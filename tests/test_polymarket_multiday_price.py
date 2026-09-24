"""Targeted frozen-protocol checks for the seven-day event and model path."""
import importlib.util
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    p=ROOT/'scripts'/name
    spec=importlib.util.spec_from_file_location(name.replace('.py',''),p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

e=load('extract_polymarket_multiday_price.py')
m=load('fit_polymarket_multiday_price.py')

def test_microsecond_cutoff_and_latest_raw_invalid():
    assert e.iso_us('2026-07-27T00:03:00.000500Z')==1785110580000500
    old=e.update(None,{'recv_us':1_000_000,'bid':.4,'ask':.6,'valid':True},'bbo')
    newest=e.update(old,{'recv_us':1_000_100,'bid':None,'ask':None,'valid':False},'bbo')
    assert e.choose(newest,1_000_200,1_000_000,'bbo')[1]=='invalid_bbo'

def test_equal_receive_conflicts_and_repeated_depth_level():
    a=e.update(None,{'recv_us':1,'bid':.4,'ask':.6,'valid':True},'bbo')
    a=e.update(a,{'recv_us':1,'bid':.4,'ask':.7,'valid':True},'bbo')
    assert e.choose(a,1,1_000_000,'bbo')[1]=='conflicting_same_receive_top'
    book=e.book_summary({'bids':[{'price':'.4','size':'2'},{'price':'.4','size':'3'}],
                         'asks':[{'price':'.6','size':'1'}]})
    assert book['reason']=='duplicate_level'

def test_inline_metadata_market_object_uses_condition_id():
    condition='0x'+'ab'*32
    assert e.metadata_condition({'market':{'conditionId':condition}})==condition
    assert e.metadata_condition({'market':condition})==condition

def test_day_equal_weights_and_offset_identity():
    rows=[{'date':'2026-07-27'},{'date':'2026-07-27'},{'date':'2026-07-28'}]
    assert np.allclose(m.day_weights(rows),[.25,.25,.5])
    p=np.array([.2,.8]);q=m.predict(np.zeros((2,1)),p,np.zeros(2))
    assert np.allclose(q,p)

def test_train_only_median_and_shared_missing_flags():
    def row(p,move):return {'p':p,'bbo_age_ms':100,'snapshot_age_ms':None,'mid_change_30s':move,
                            'depth':None,'imbalance':None,'spread':.02,'date':'2026-07-27'}
    train=[row(.2,-.1),row(.4,.1),row(.6,None),row(.8,None)]
    design=m.Design(train)
    assert design.medians['mid_change_30s']==0.0
    later=[row(.3,10.0)]
    mat=design.transform(later)
    assert mat['R1'].shape==(1,7) and mat['R2'].shape==(1,9) and mat['R3'].shape==(1,11)
