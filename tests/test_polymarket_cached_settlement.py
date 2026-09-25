"""Required closeout correctness cases, using synthetic input and cached replies."""
import importlib.util,json
from pathlib import Path
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v=load('verify_polymarket_multiday_ctf');m=load('fit_polymarket_multiday_price')
def spec(i):return v.call_spec('0x'+f'{i:064x}','0x'+'aa'*32,i)
def response(body,fail=False):
    return json.dumps([{'jsonrpc':'2.0','id':q['id'],**({'error':{'code':-1}} if fail and q['id']==2 else {'result':'0x'+f"{int(q['params'][0]['data'],16):064x}"})} for q in body]).encode()
def test_resume_partial_retry_semantic_cache_and_durable_count(tmp_path):
    sent=[]
    def transport(body):
        # Reservation must already exist on disk before transport sees request.
        ledger=json.loads((tmp_path/'ledger.json').read_text())
        assert ledger['http_requests']==len(sent)+1
        sent.append(body);return 200,response(body,len(sent)==1),0,None
    rpc=v.Rpc(tmp_path,10**12,transport,sleeper=lambda _:None)
    rpc.call([spec(1),spec(2),spec(3)])
    assert [len(x) for x in sent]==[3,1]
    assert rpc.ledger['logical_calls']==4 and rpc.ledger['retry_logical_calls']==1
    again=v.Rpc(tmp_path,10**12,lambda _:pytest.fail('cache hit sent'),sleeper=lambda _:None)
    assert again.get(spec(2))=='0x'+f'{2:064x}'
    again.call([spec(3),spec(1),spec(2)])
    assert again.ledger['logical_calls']==4
    changed=spec(1);changed['block_tag']='0x12'
    assert again.get(changed) is None

def test_response_rejects_duplicates_errors_and_malformed_hex():
    req=[{'id':1,'spec':spec(1)},{'id':2,'spec':spec(2)}]
    one={'jsonrpc':'2.0','id':1,'result':'0x'+'00'*32}
    with pytest.raises(ValueError):v.validate([one,one],req)
    good,bad=v.validate([one,{'jsonrpc':'2.0','id':2,'error':{},'result':'0x'+'00'*32}],req)
    assert set(good)=={1} and set(bad)=={2}
    for invalid in ('0x1','0x'+'gg'*32,3,None):assert not v.valid_result(invalid,spec(1))

def test_three_attempts_exhaustion_survives_restart(tmp_path):
    def bad(body):return 429,b'[]',0,None
    rpc=v.Rpc(tmp_path,10**12,bad,sleeper=lambda _:None);rpc.call([spec(1)])
    assert rpc.ledger['logical_calls']==3
    resumed=v.Rpc(tmp_path,10**12,lambda _:pytest.fail('exhausted resent'),sleeper=lambda _:None)
    resumed.call([spec(1)]);assert resumed.ledger['logical_calls']==3

def test_direction_not_condition_membership_and_reversed_tokens():
    e={'up_token':'2','down_token':'1'}
    i,status=v.direction(e,['0x'+f'{1:064x}','0x'+f'{2:064x}'])
    assert (i,status)==(1,'verified')
    assert v.label(i,[0,7,7],status,[.3,.7])==('verified_binary',1,False)
    assert v.label(None,[1,0,1],'verified')[1] is None
    assert v.direction(e,[None,None])[1]=='identity_query_failed'
    assert v.direction(e,['0x3','0x4'])[1]=='identity_contradiction'

def test_settlement_scaling_unresolved_and_nonbinary():
    assert v.label(0,[1,0,1],'verified')[:2]==v.label(0,[9,0,9],'verified')[:2]
    for vec,status in (([0,0,0],'unresolved'),([1,1,2],'nonbinary_payout'),([1,0,2],'invalid_payout'),([None,0,1],'payout_query_failed')):
        assert v.label(0,vec,'verified')[:2]==(status,None)

def test_check_day_labels_cannot_change_model_or_transform():
    def rows(day,n):
        return [{'slot':i,'date':day,'p':.15+.7*(i%17)/16,'y':i%2,'bbo_age_ms':i%99,
                 'snapshot_age_ms':20,'depth':None if i%7==0 else 1+i,'imbalance':.1,
                 'mid_change_30s':None if i%5==0 else .01*(i%3-1),'spread':.02} for i in range(n)]
    tr=rows(m.TRAIN[0],60)+rows(m.TRAIN[1],55)+rows(m.TRAIN[2],50)
    cal=rows(m.CAL,40);fw=rows(m.FORWARD[0],40)
    def pipeline(fw):
        design=m.Design(tr);tm=design.transform(tr);cm=design.transform(cal);fm=design.transform(fw)
        yt,pt=m.arrays(tr);yc,pc=m.arrays(cal);_,pf=m.arrays(fw);out={}
        for arm in ('R1','R2','R3'):
            options=[]
            for C in m.CS:
                beta=m.fit(tm[arm],yt,pt,m.day_weights(tr),C)
                options.append((m.loss(yc,m.predict(cm[arm],pc,beta)).mean(),C,beta))
            best=min(options,key=lambda a:(a[0],a[1]));out[arm]=(best[1],best[2],m.predict(fm[arm],pf,best[2]))
        assert np.allclose(tm['R1'],tm['R2'][:,:7]) and np.allclose(tm['R2'],tm['R3'][:,:9])
        return out,design.knots.copy(),design.medians.copy()
    a,ka,ma=pipeline(fw)
    for row in fw:row['y']=1-row['y']
    b,kb,mb=pipeline(fw)
    for arm in a:
        assert a[arm][0]==b[arm][0]
        np.testing.assert_array_equal(a[arm][1],b[arm][1]);np.testing.assert_array_equal(a[arm][2],b[arm][2])
    np.testing.assert_array_equal(ka,kb);assert ma==mb

def test_interrupted_saved_response_recovers_without_resending(tmp_path):
    def interrupted(body):
        v.atomic(tmp_path/'reply_00001.json',{'http_status':200,'body':response(body).decode(),'error':None})
        raise RuntimeError('simulated interruption after response save')
    rpc=v.Rpc(tmp_path,10**12,interrupted,sleeper=lambda _:None)
    with pytest.raises(RuntimeError):rpc.call([spec(1)])
    resumed=v.Rpc(tmp_path,10**12,lambda _:pytest.fail('saved success resent'),sleeper=lambda _:None)
    resumed.call([spec(1)])
    assert resumed.ledger['logical_calls']==1 and resumed.ledger['http_requests']==1
    assert resumed.ledger['response_bytes']>0 and resumed.ledger['unknown_response_bytes_reserved']==0

def test_interrupted_unknown_response_is_conservatively_charged(tmp_path):
    def interrupted(body):raise RuntimeError('simulated post-send interruption')
    rpc=v.Rpc(tmp_path,10**12,interrupted,sleeper=lambda _:None)
    with pytest.raises(RuntimeError):rpc.call([spec(1)])
    resumed=v.Rpc(tmp_path,10**12,sleeper=lambda _:None)
    assert resumed.ledger['logical_calls']==1 and resumed.ledger['unknown_response_bytes_reserved']==1048576
