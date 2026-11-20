import json,unittest
from cs769.models.edits import compact_graph as old, paired_graph as new
class PairTests(unittest.TestCase):
 def text(self,rows,tail="links: e2 -> e4\n"):
  return old.HEADER+"fence=3\nTURN t1\n"+"\n".join(rows)+"\nEND_RECORDS\n"+tail
 def row(self,id,kind,v):return id+" "+kind+" "+json.dumps(v,ensure_ascii=False,separators=(",",":"))
 def test_roundtrip_payload_ids_errors(self):
  for error in [[],[True],[False]]:
   x=self.text([self.row("e0","U","keep ID 123 and constraint"),self.row("e1","C",["call_abc","g1","tool",'{"id":"123"}']),self.row("e2","R",["e1",'{"nested":"a\\nb"}']+error),self.row("e3","A","unverified text retained")])
   y=new.encode(x);self.assertIn("e1/e2 X",y);self.assertEqual(new.decode(y),x)
 def test_parallel_order_not_changed(self):
  x=self.text([self.row("e0","C",["a","g0","one","{}"]),self.row("e1","C",["b","g0","two","{}"]),self.row("e2","R",["e0","first"]),self.row("e3","R",["e1","second"])])
  self.assertEqual(new.encode(x),x)
 def test_mixed_preserves_unpaired_and_group(self):
  x=self.text([self.row("e0","C",["a","g0","one","{}"]),self.row("e1","C",["b","g0","two","{}"]),self.row("e2","R",["e1","second"]),self.row("e3","R",["e0","first"])])
  self.assertIn(new.MIXED,new.encode(x));self.assertEqual(new.decode(new.encode(x)),x)
 def test_no_fusion_across_turn(self):
  x=self.text([self.row("e0","C",["a","g0","one","{}"]),"TURN t2",self.row("e1","R",["e0","x"])])
  self.assertEqual(new.encode(x),x)
 def test_unknown_and_no_calls(self):
  for x in ["other layout",self.text([self.row("e0","A","intact")])]:self.assertEqual(new.encode(x),x)
if __name__=="__main__":unittest.main()
