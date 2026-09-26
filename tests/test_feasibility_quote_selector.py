"""Synthetic tests of exact functions used by the running fixed-hour extractor."""
import ast,datetime as dt,json,math,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts'/'extract_feasibility_quotes.py';tree=ast.parse(p.read_text());ns={'dt':dt,'math':math}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('us','add','num','quote_status')],type_ignores=[]),str(p),'exec'),ns)
class QuoteTests(unittest.TestCase):
 def setUp(self):ns['states']={};ns['bytoken']={'t':{'decision_us':1000000}}
 def add(self,recv,bid=.3,ask=.4):ns['add']('t','direct_bbo',recv,bid,ask,None,'f')
 def test_future_submillisecond(self):
  self.add(1000001);self.assertEqual(ns['states'],{})
 def test_exact_boundary(self):
  self.add(1000000);self.assertEqual(ns['states'][('t','direct_bbo')]['receive_us'],1000000)
 def test_latest_invalid_blocks_old(self):
  self.add(900000);self.add(950000,None,None);self.add(800000);self.assertIsNone(ns['states'][('t','direct_bbo')]['bid'])
 def test_same_price_not_conflict(self):
  self.add(900000);self.add(900000);self.assertEqual(len(ns['states'][('t','direct_bbo')]['pairs']),1)
 def test_different_price_conflict(self):
  self.add(900000);self.add(900000,.2,.5);self.assertEqual(len(ns['states'][('t','direct_bbo')]['pairs']),2)
 def test_timezone_precision(self):
  self.assertEqual(ns['us']('1970-01-01T00:00:01.000001Z'),1000001)
  self.assertEqual(ns['us']('1969-12-31T19:00:01.000001-05:00'),1000001)
 def test_boundary_and_locked_are_not_valid(self):
  for bid,ask in [(0,.5),(.5,1),(.5,.5)]:
   self.assertEqual(ns['quote_status']({'bid':bid,'ask':ask,'pairs':[[bid,ask]]},'direct_bbo'),'boundary_or_locked_latest')
 def test_strict_interior_is_valid(self):
  self.assertEqual(ns['quote_status']({'bid':.3,'ask':.4,'pairs':[[.3,.4]]},'direct_bbo'),'valid')
 def test_nonfinite_and_crossed_not_valid(self):
  for bid,ask in [(float('nan'),.5),(.6,.5)]:
   self.assertEqual(ns['quote_status']({'bid':bid,'ask':ask,'pairs':[[bid,ask]]},'direct_bbo'),'invalid_latest')
 def test_snapshot_never_certifies_quote(self):
  self.assertEqual(ns['quote_status']({'bid':.3,'ask':.4,'pairs':[[.3,.4]]},'snapshot_top'),'diagnostic_unvalidated')
if __name__=='__main__':unittest.main()
