import csv
import pytest
from train_behavior import train
FIELDS=['session_id','split','dwell_seconds','zone_entries','observed_seconds','label']
def write(path,rows):
    with path.open('w') as f:
        w=csv.writer(f); w.writerow(FIELDS); w.writerows(rows)
def test_empty_rejected(tmp_path):
    f=tmp_path/'empty.csv'; write(f,[])
    with pytest.raises(ValueError,match='No labeled'): train(f,tmp_path/'out')
def test_session_leakage(tmp_path):
    f=tmp_path/'leak.csv'
    write(f,[[ 'same',s,1,1,2,'ordinary_activity'] for s in ['train','val','test']])
    with pytest.raises(ValueError,match='leakage'): train(f,tmp_path/'out')
def test_training_execution_only(tmp_path):
    # Synthetic plumbing fixture, never evidence of real-world accuracy.
    rows=[]
    for s in ['train','val','test']:
        rows.extend([[s,s,1,1,3,'ordinary_activity'],[s,s,20,4,30,'review_activity']])
    f=tmp_path/'fixture.csv'; write(f,rows)
    result=train(f,tmp_path/'out')
    assert (tmp_path/'out'/'behavior.joblib').exists()
    assert 'test' in result
