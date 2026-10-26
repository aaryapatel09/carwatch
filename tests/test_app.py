"""Run Streamlit's public testing API in an isolated data directory."""

import os
import subprocess
import sys
from pathlib import Path


def test_all_pages_and_persisted_review(tmp_path):
    script = r"""
from streamlit.testing.v1 import AppTest
from store import ROOT,new_run,set_status,write_json,read_json
from config import CameraConfig
from demo import synthetic_dataset
ROOT.mkdir(parents=True,exist_ok=True)
source=ROOT/'fixture.mp4'; source.write_bytes(b'fixture, never decoded')
meta,out=new_run(source,CameraConfig().to_dict(),'UI fixture',origin='sample')
row=synthetic_dataset(per_class=2)[0]; row.update(label='unreviewed',label_source=None)
write_json(out/'windows.json',[row])
write_json(out/'report.json',dict(duration_seconds=8,sampled_frames=32,events=[]))
set_status(out,'complete')
app=AppTest.from_file('app.py').run(timeout=30)
for page in ['Analyze video','Live camera','Review & label','Train models','Settings','Overview']:
    app.sidebar.radio[0].set_value(page).run(timeout=30)
    assert not app.exception,(page,app.exception)
    if page=='Live camera':
        assert next(b for b in app.button if b.label=='Start camera').disabled
    if page=='Train models':
        assert next(b for b in app.button if b.label=='Train custom model').disabled
app.sidebar.radio[0].set_value('Review & label').run(timeout=30)
next(s for s in app.selectbox if s.label=='Human label').set_value('ordinary_activity')
next(b for b in app.button if b.label=='Save window label').click().run(timeout=30)
assert not app.exception
assert read_json(out/'windows.json')[0]['label']=='ordinary_activity'
app.sidebar.radio[0].set_value('Train models').run(timeout=30)
assert next(b for b in app.button if b.label=='Train custom model').disabled
print('All app sections and review persistence passed; sample labels excluded from real training')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "CARWATCH_DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
