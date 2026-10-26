"""Generated feature sequences to exercise training; no recorded people or safety evidence."""
import numpy as np
from features import SCHEMA, LABELS, STEPS, NAMES


def synthetic_dataset(seed=42,per_class=16):
    rng=np.random.default_rng(seed)
    rows=[]
    for split in ('train','val','test'):
        for label in LABELS:
            for i in range(per_class):
                a=np.zeros((STEPS,len(NAMES)),dtype=float)
                a[:,0]=1; a[:,2]=rng.uniform(.4,.6); a[:,3]=.85
                a[:,6]=.18+rng.normal(0,.005,STEPS); a[:,7]=.5
                if label=='ordinary_activity':
                    a[:,2]=np.linspace(.05,.95,STEPS); a[:,1]=(a[:,2]>.4)&(a[:,2]<.6); a[:,8]=.12
                elif label=='lingering':
                    a[:,1]=1
                elif label=='repeated_approach':
                    a[:,2]=.5+.35*np.sin(np.linspace(0,6*np.pi,STEPS))
                    a[:,1]=abs(a[:,2]-.5)<.22; a[1:,8]=np.diff(a[:,2])*4
                elif label=='hand_near_zone':
                    a[:,1]=1; a[:,4]=1; a[5:27,5]=1
                # Mild sensor noise and occasional missing frames, still an artificial exercise.
                a[:,2:4]+=rng.normal(0,.015,(STEPS,2))
                a[rng.choice(STEPS,2,replace=False)]=0
                rows.append(dict(id=f'{split}-{label}-{i}',track=i,start=0,end=8,schema=SCHEMA,
                                 session_id=f'generated-{split}',video_hash=f'generated-{split}-{label}-{i}',
                                 split=split,origin='synthetic',label=label,label_source='generator',sequence=a.tolist()))
    return rows

if __name__=='__main__':
    from temporal import fit
    from store import ROOT,write_json
    rows=synthetic_dataset()
    out=ROOT/'models'/'synthetic-demo'
    result=fit(rows,out,epochs=50,allow_synthetic=True)
    write_json(out/'synthetic_sequences.json',rows)
    print('Synthetic-only GRU trained. Held-out generated-window accuracy:',result['test']['report']['accuracy'])
    print('This measures generated patterns, not real-world behavior. Saved:',out)
