"""Small custom GRU activity classifier, with provenance and grouped evaluation."""
from pathlib import Path
import copy
import hashlib
import json
import numpy as np
import torch
from torch import nn
from features import SCHEMA, STEPS, NAMES, LABELS, validate_sequence
from store import write_json


class ActivityNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru=nn.GRU(len(NAMES),32,batch_first=True)
        self.head=nn.Linear(32,len(LABELS))

    def forward(self,x):
        output,_=self.gru(x)
        return self.head(output.mean(dim=1))


def validate_dataset(rows,allow_synthetic=False):
    if not rows: raise ValueError('No human-labeled clips yet. Review recordings first.')
    sessions={}; hashes={}; seen=set()
    for row in rows:
        if row.get('schema')!=SCHEMA: raise ValueError('Feature schema mismatch')
        sequence=validate_sequence(row['sequence'])
        if sequence[:,0].sum()<4:
            raise ValueError('Each window needs at least four observed frames')
        if row.get('label') not in LABELS: raise ValueError('Unsupported activity label')
        if row.get('split') not in ('train','val','test'): raise ValueError('Invalid dataset split')
        if not row.get('session_id') or not row.get('video_hash'): raise ValueError('Missing session or recording fingerprint')
        if row.get('origin')!='real' and not allow_synthetic:
            raise ValueError('Real-data training excludes synthetic and example footage')
        if not allow_synthetic and row.get('label_source')!='human':
            raise ValueError('Real-data training requires human-reviewed labels')
        for table,key in [(sessions,row['session_id']),(hashes,row['video_hash'])]:
            old=table.setdefault(key,row['split'])
            if old!=row['split']: raise ValueError('Recording/session leakage between dataset splits')
        key=(row['video_hash'],row['track'],row['start'])
        if key in seen: raise ValueError('Duplicate recording window; remove duplicate analysis labels')
        seen.add(key)
    counts={split:{label:sum(r['split']==split and r['label']==label for r in rows) for label in LABELS} for split in ('train','val','test')}
    if any(n<2 for c in counts.values() for n in c.values()):
        raise ValueError('Need at least 2 reviewed clips of each of the 4 activities in each split (24 clips minimum). This is only a training floor, not sufficient validation.')
    return counts


def classification_metrics(y,pred):
    from sklearn.metrics import classification_report,confusion_matrix
    return dict(report=classification_report(y,pred,labels=list(range(len(LABELS))),target_names=LABELS,output_dict=True,zero_division=0),
                confusion_matrix=confusion_matrix(y,pred,labels=list(range(len(LABELS)))).tolist())


def fit(rows,out,epochs=60,allow_synthetic=False,progress=None):
    if not 1<=epochs<=300: raise ValueError('Epochs must be between 1 and 300')
    counts=validate_dataset(rows,allow_synthetic)
    torch.manual_seed(42)
    torch.set_num_threads(2)
    def split(name):
        data=[r for r in rows if r['split']==name]
        return torch.tensor(np.array([r['sequence'] for r in data]),dtype=torch.float32),torch.tensor([LABELS.index(r['label']) for r in data])
    x,y=split('train'); vx,vy=split('val'); tx,ty=split('test')
    # Fit standardization on observed TRAIN frames only; keep missing rows zero.
    visible=x[:,:,0]>0
    mean=x[visible].mean(0); std=x[visible].std(0,unbiased=False).clamp(min=.05)
    mean[0]=0; std[0]=1
    def normalize(a): return ((a-mean)/std)*a[:,:,:1]
    x,vx,tx=normalize(x),normalize(vx),normalize(tx)
    model=ActivityNet()
    weights=1/torch.bincount(y,minlength=len(LABELS)).float()
    loss_fn=nn.CrossEntropyLoss(weight=weights/weights.mean())
    opt=torch.optim.AdamW(model.parameters(),lr=.008,weight_decay=.001)
    best=copy.deepcopy(model.state_dict()); best_loss=float('inf'); best_epoch=0; history=[]
    for epoch in range(epochs):
        model.train()
        order=torch.randperm(len(x))
        losses=[]
        for idx in order.split(32):
            opt.zero_grad(); loss=loss_fn(model(x[idx]),y[idx]); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),1.)
            opt.step(); losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad(): val_loss=float(loss_fn(model(vx),vy))
        history.append(dict(epoch=epoch+1,train_loss=sum(losses)/len(losses),val_loss=val_loss))
        if val_loss<best_loss:
            best_loss=val_loss; best=copy.deepcopy(model.state_dict()); best_epoch=epoch+1
        if progress: progress((epoch+1)/epochs,history[-1])
    model.load_state_dict(best); model.eval()
    origin='synthetic_demo' if any(r['origin']!='real' for r in rows) else 'real_experimental'
    report=dict(schema=SCHEMA,origin=origin,status='research only; not safety validated',labels=LABELS,features=NAMES,
                counts=counts,epochs=epochs,best_epoch=best_epoch,history=history,
                sessions={s:sorted({r['session_id'] for r in rows if r['split']==s}) for s in counts},
                dataset_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
                limitations=['Window classification, not intent or confirmed contact','Test clips must be from separate recording sessions','No deployment false-alert rate measured'])
    with torch.no_grad():
        for name,a,b in [('val',vx,vy),('test',tx,ty)]:
            logits=model(a); pred=logits.argmax(1)
            report[name]=classification_metrics(b.numpy(),pred.numpy())
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    # State dict only; inference uses weights_only to avoid arbitrary pickle objects.
    torch.save({'state_dict':best,'mean':mean,'std':std},out/'weights.pt')
    write_json(out/'model.json',report)
    write_json(out/'dataset_manifest.json',[{k:v for k,v in r.items() if k!='sequence'} for r in rows])
    return report


class Predictor:
    def __init__(self,path,allow_demo=False):
        path=Path(path)
        self.card=json.loads((path/'model.json').read_text())
        if self.card['schema']!=SCHEMA: raise ValueError('Model feature schema mismatch')
        if self.card['origin']!='real_experimental' and not allow_demo:
            raise ValueError('Synthetic demo models cannot score real footage')
        weights=torch.load(path/'weights.pt',map_location='cpu',weights_only=True)
        self.mean,self.std=weights['mean'],weights['std']
        self.model=ActivityNet(); self.model.load_state_dict(weights['state_dict']); self.model.eval()

    def predict(self,sequence):
        x=torch.tensor(validate_sequence(sequence)).unsqueeze(0)
        x=((x-self.mean)/self.std)*x[:,:,:1]
        with torch.no_grad(): probs=self.model(x).softmax(1)[0].tolist()
        i=int(np.argmax(probs))
        return dict(label=LABELS[i],score=round(probs[i],4),scores=dict(zip(LABELS,probs)),
                    note='Uncalibrated model score; not probability of danger')
