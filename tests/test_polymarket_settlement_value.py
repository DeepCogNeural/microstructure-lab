import importlib.util,unittest
from decimal import Decimal as D
from pathlib import Path
spec=importlib.util.spec_from_file_location('p1',(Path(__file__).with_name('polymarket_settlement_value.py') if Path(__file__).with_name('polymarket_settlement_value.py').exists() else Path(__file__).resolve().parents[1]/'scripts'/'polymarket_settlement_value.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SettlementTests(unittest.TestCase):
 def test_buy_sell(self):
  self.assertEqual(m.gross('.48',1,1),D(52));self.assertEqual(m.gross('.48',-1,1),D(-52))
 def test_complement(self):
  for sign in [-1,1]:
   for y in [0,1]:
    q,s=m.up_equivalent(D('.27'),sign,False);self.assertEqual(m.gross('.27',sign,1-y),m.gross(q,s,y))
 def test_invalid(self):
  for q,s,y in [('NaN',1,0),('1.1',1,0),('.5',0,1),('.5',1,2)]:
   with self.assertRaises(ValueError):m.gross(q,s,y)
 def test_boundaries(self):self.assertEqual([m.bucket(D(q)) for q in ['0','.2','.4','.6','.8','1']],[0,1,2,3,4,4])
 def test_label_direction(self):
  x={'identity_status':'verified','label_status':'verified_binary','payout_vector':[0,5,5],'up_outcome_index':1,'y':1};self.assertEqual(m.label_value(x),1)
  x['y']=0
  with self.assertRaises(ValueError):m.label_value(x)
 def test_weighting(self):
  rows=[{'slot':1,'group':1,'shares':D(100),'value':D(1000)},{'slot':2,'group':2,'shares':D(1),'value':D(-20)}]
  s=m.summary(rows);self.assertEqual(s['event_equal_cents'],-5);self.assertAlmostEqual(s['share_weighted_cents'],980/101)
 def test_unresolved_not_zero(self):
  self.assertIsNone(m.label_value({'identity_status':'verified','label_status':'unresolved'}))
class GroupTests(unittest.TestCase):
 def fixture(self):
  leg={'key':[137,'contract','tx',1],'token':'u','shares':'2','price':'.25','sign':1}
  g={'tx':'tx','contract':'contract','match_log_index':3,'failure':[],'taker':{'log_index':2,'chain_id':137,'contract':'contract','decoded':{'tokenId':'u'}},'maker_legs':[leg]}
  e={'2026-07-28':{'groups':[g],'joined_print_indices':[[0,0,'tx','contract',3]],'selected_24_by_category':{},'token_slug':{'u':'slug','d':'slug'},'prints':[{}],'unmatched':[],'active_slugs':['slug']}}
  r={'1':{'up_token':'u','down_token':'d','date':'2026-07-28','slug':'slug','condition_id':'condition'}}
  labels=[{'slot':1,'identity_status':'verified','label_status':'verified_binary','payout_vector':[1,0,1],'up_outcome_index':0,'y':1}]
  return e,r,labels,g
 def test_duplicate_leg_conflict(self):
  e,r,l,g=self.fixture();g['maker_legs'].append({**g['maker_legs'][0],'price':'.5'})
  with self.assertRaises(ValueError):m.analyze(e,r,l)
 def test_taker_excluded(self):
  e,r,l,g=self.fixture();g['maker_legs'][0]['key'][3]=2
  with self.assertRaises(ValueError):m.analyze(e,r,l)
 def test_unknown_token_quarantines_group(self):
  e,r,l,g=self.fixture();g['maker_legs'][0]['token']='unknown';a,rows=m.analyze(e,r,l)
  self.assertEqual(rows,[]);self.assertEqual(a['excluded']['maker_token_not_verified_groups'],1)
 def test_duplicate_identical_not_double_counted(self):
  e,r,l,g=self.fixture();g['maker_legs'].append(dict(g['maker_legs'][0]));a,rows=m.analyze(e,r,l)
  self.assertEqual(len(rows),1);self.assertEqual(a['funnel']['2026-07-28']['duplicate_legs'],1)
if __name__=='__main__':unittest.main()
