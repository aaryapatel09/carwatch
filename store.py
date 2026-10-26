"""Local persisted runs. No public listener or external data service."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent/'runtime'


def write_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False))
    os.replace(temp,path)


def read_json(path,default=None):
    path=Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def run_dir(run_id,root=ROOT):
    if len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid run ID')
    return Path(root)/'runs'/run_id


def new_run(source,config,session_id,split='train',origin='real',root=ROOT):
    if split not in ('train','val','test'):
        raise ValueError('Invalid dataset split')
    if origin not in ('real','synthetic','sample') or not session_id.strip():
        raise ValueError('Recording group and origin are required')
    source=Path(source)
    h=hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    run_id=uuid.uuid4().hex
    out=run_dir(run_id,root)
    out.mkdir(parents=True)
    source_name='source'+source.suffix.lower()
    shutil.copyfile(source,out/source_name)
    info=dict(id=run_id,created=datetime.now(timezone.utc).isoformat(),status='queued',camera=config['name'],
              session_id=session_id.strip(),split=split,origin=origin,video_hash=h.hexdigest(),source=source_name,config=config)
    write_json(out/'meta.json',info)
    return info,out


def list_runs(root=ROOT):
    result=[]
    for path in (Path(root)/'runs').glob('*/meta.json'):
        item=read_json(path)
        if item: result.append(item)
    return sorted(result,key=lambda x:x['created'],reverse=True)


def set_status(out,status,**fields):
    info=read_json(Path(out)/'meta.json')
    info.update(status=status,**fields)
    write_json(Path(out)/'meta.json',info)


def save_review(out,window_id,label):
    from features import LABELS
    if label not in LABELS+['unreviewed','exclude']:
        raise ValueError('Unknown activity label')
    data=read_json(Path(out)/'windows.json',[])
    found=False
    for item in data:
        if item['id']==window_id:
            item.update(label=label,label_source='human' if label not in ('unreviewed','exclude') else None)
            found=True
    if not found: raise ValueError('Window not found')
    write_json(Path(out)/'windows.json',data)


def dataset_rows(root=ROOT,real_only=False):
    rows=[]
    for meta in list_runs(root):
        if meta['status']!='complete' or (real_only and meta['origin']!='real'): continue
        for w in read_json(run_dir(meta['id'],root)/'windows.json',[]):
            if w.get('label_source')!='human' or w['label'] in ('unreviewed','exclude'): continue
            rows.append({**w,**{k:meta[k] for k in ('session_id','split','origin','video_hash')},'run_id':meta['id']})
    return rows


def delete_run(run_id,root=ROOT):
    out=run_dir(run_id,root)
    if out.exists(): shutil.rmtree(out)
