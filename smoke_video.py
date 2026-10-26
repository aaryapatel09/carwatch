"""Synthetic blank-video integration check. Not an accuracy benchmark."""
import tempfile
from pathlib import Path
import cv2
import numpy as np
from vision import analyze
with tempfile.TemporaryDirectory() as td:
    root=Path(td); source=root/'blank.avi'
    writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),10,(320,240))
    assert writer.isOpened()
    for _ in range(12): writer.write(np.zeros((240,320,3),dtype=np.uint8))
    writer.release()
    report=analyze(source,root/'out',(.2,.2,.8,.95))
    assert report['frames']==12 and not report['events']
    print('PASS: actual detector + tracking + video decode + JSON export (12 blank frames). No real-world accuracy claim.')
