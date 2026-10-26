"""Actual pose-CV integration on a bundled still-image replay; not field evaluation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import cv2
import ultralytics
from config import CameraConfig
from vision import analyze
from store import ROOT,new_run,set_status,read_json,save_review,dataset_rows,write_json
from media import extract_track_clip

with tempfile.TemporaryDirectory() as temp:
    source=Path(temp)/'sample.avi'
    img=cv2.imread(str(Path(ultralytics.__file__).parent/'assets'/'bus.jpg'))
    img=cv2.resize(img,(480,640))
    writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),8,(480,640))
    assert writer.isOpened()
    for _ in range(80): writer.write(img)
    writer.release()
    config=CameraConfig(name='Example replay · not a car test',zone=(.01,.01,.99,.99),hand_zone=(.1,.2,.9,.9),dwell=2.,pose=True)
    meta,out=new_run(source,config.to_dict(),'bundled-image-replay','train','sample')
    set_status(out,'processing')
    report=analyze(out/meta['source'],out,config=config,max_seconds=10)
    windows=read_json(out/'windows.json')
    assert report['sampled_frames']==40
    assert report['events'] and windows
    assert all(e['clip'] and (out/e['clip']).exists() for e in report['events'])
    window=windows[0]
    clip=extract_track_clip(out/meta['source'],out/f"window-{window['id']}.mp4",window['start'],window['end'],read_json(out/'samples.json'),window['track'])
    cap=cv2.VideoCapture(str(clip)); ok,frame=cap.read(); cap.release(); assert ok
    set_status(out,'complete')
    save_review(out,window['id'],'ordinary_activity')
    assert any(r['run_id']==meta['id'] for r in dataset_rows())
    save_review(out,window['id'],'unreviewed')
    verification=dict(status='passed',origin='bundled still-image replay',run_id=meta['id'],pose_frames=report['sampled_frames'],events=len(report['events']),windows=len(windows),checks=['decode','pose tracking','zone and wrist rules','event clips','annotated window clip','persisted human review','dataset export'],limitation='No real car footage or field accuracy evaluation')
    write_json(ROOT/'verification.json',verification)
    print(verification)
