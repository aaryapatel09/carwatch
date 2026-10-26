"""Opt-in local camera monitor. No external messages or recording until explicitly started."""
from pathlib import Path
import threading
import time
import uuid
import cv2
from config import CameraConfig
from engine import ActivityEngine
from store import ROOT,write_json


class LiveMonitor:
    def __init__(self):
        self.lock=threading.Lock()
        self.stop_event=threading.Event()
        self.thread=None
        self._state=dict(status='idle',frame=None,events=[],error=None,elapsed=0.,last_frame=None)

    def snapshot(self):
        with self.lock:
            return {**self._state,'events':list(self._state['events'])}

    def start(self,camera,config,minutes=2):
        if not isinstance(camera,int) or not 0<=camera<=9:
            raise ValueError('Choose a local camera index between 0 and 9')
        if not 1<=minutes<=10: raise ValueError('Live sessions must last 1–10 minutes')
        config.validate()
        if self.thread and self.thread.is_alive(): raise ValueError('A camera session is already running')
        self.stop_event.clear()
        with self.lock:
            self._state=dict(status='starting',frame=None,events=[],error=None,elapsed=0.,last_frame=None)
        self.thread=threading.Thread(target=self._run,args=(camera,config,minutes),daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=1.)
        with self.lock:
            if self.thread and self.thread.is_alive(): self._state['status']='stopping'

    def _run(self,camera,config,minutes):
        cap=None
        out=ROOT/'live'/uuid.uuid4().hex
        out.mkdir(parents=True,exist_ok=True)
        started=time.monotonic()
        try:
            from ultralytics import YOLO
            weights=Path(__file__).parent/('yolo11n-pose.pt' if config.pose else 'yolo11n.pt')
            model=YOLO(str(weights))
            if self.stop_event.is_set(): return
            cap=cv2.VideoCapture(camera)
            if not cap.isOpened(): raise RuntimeError('Camera could not be opened. Check the device and macOS camera permission.')
            engine=ActivityEngine(zone=config.zone,dwell=config.dwell,repeat=config.repeat,window=config.window,
                                  hand_zone=config.hand_zone if config.pose else None,hand_seconds=config.hand_seconds)
            next_sample=0.; events=[]
            while not self.stop_event.is_set() and time.monotonic()-started<minutes*60:
                ok,frame=cap.read()
                if not ok: raise RuntimeError('Camera stopped delivering frames')
                t=time.monotonic()-started
                if t<next_sample:
                    self.stop_event.wait(.01); continue
                next_sample=t+.25
                h,w=frame.shape[:2]
                r=model.track(frame,persist=True,classes=[0],conf=config.confidence,tracker='bytetrack.yaml',verbose=False)[0]
                people=[]
                if r.boxes.id is not None:
                    poses=r.keypoints.data.cpu().tolist() if r.keypoints is not None else None
                    for idx,(tid,box) in enumerate(zip(r.boxes.id.cpu().tolist(),r.boxes.xyxy.cpu().tolist())):
                        b=[box[0]/w,box[1]/h,box[2]/w,box[3]/h]; wrists=[]
                        if poses:
                            for k in (9,10):
                                x,y,c=poses[idx][k]
                                if c>=.5 and 0<x<w and 0<y<h: wrists.append((x/w,y/h))
                        people.append((int(tid),b,wrists))
                new=engine.update(t,people)
                annotated=r.plot()
                for rect,color in [(config.zone,(125,225,165)),(config.hand_zone,(80,180,250))]:
                    a,b,c,d=rect; cv2.rectangle(annotated,(int(a*w),int(b*h)),(int(c*w),int(d*h)),color,2)
                for event in new:
                    event['id']=f'e{len(events):04d}'
                    if len(events)<100:
                        event['image']=event['id']+'.jpg'; cv2.imwrite(str(out/event['image']),annotated)
                        events.append(event)
                ok,encoded=cv2.imencode('.jpg',annotated)
                with self.lock:
                    self._state.update(status='running',frame=encoded.tobytes() if ok else None,events=list(events),elapsed=t,last_frame=time.time(),output=str(out))
                write_json(out/'session.json',dict(status='running',camera=config.name,config=config.to_dict(),events=events,elapsed=t))
        except Exception as exc:
            with self.lock: self._state.update(status='error',error=str(exc))
        finally:
            if cap is not None: cap.release()
            with self.lock:
                if self._state['status']!='error': self._state['status']='stopped'
                final={k:v for k,v in self._state.items() if k!='frame'}
            write_json(out/'session.json',final)
