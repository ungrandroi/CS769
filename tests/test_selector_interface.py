import unittest
from copy import deepcopy
from cs769.models.edits import selector_interface as si, dependency_slice as ds
from cs769.cli import counter
class InterfaceTests(unittest.TestCase):
    def setUp(self):self.count=counter("o200k_base")
    def test_exact_roundtrip_and_positive_saving(self):
        value={"description":"long description with distinct facts "*100,"id":"ABC"}
        p={"events":[deepcopy(value) for _ in range(5)],"current":{"id":"XYZ"}}
        before=deepcopy(p);packed,yes=si.pack(p,self.count)
        self.assertTrue(yes);self.assertEqual(si.restore(packed),p);self.assertEqual(p,before)
        self.assertLess(self.count(si.dumps(packed))+self.count(si.NOTE),self.count(si.dumps(p)))
    def test_small_and_collision_fallback(self):
        for p in [{"small":1},{"$shared":"literal","x":["abc"*100]*5}]:
            out,yes=si.pack(p,self.count);self.assertFalse(yes);self.assertEqual(out,p)
    def test_only_interface_changes(self):
        p={"x":"hello","fields":[{"id":"g8:1:3","eligible":True}]};wire={"model":"gpt-4.1","messages":[{"role":"system","content":ds.SYSTEM_PROMPT},{"role":"user","content":si.dumps(p)}],"temperature":0,"seed":42,"max_tokens":2048}
        out=si.request(wire,p,self.count)
        self.assertIn(ds.SYSTEM_PROMPT.split("Read only",1)[1],out["messages"][0]["content"])
        self.assertEqual({k:v for k,v in out.items() if k not in ("messages","response_format")},{k:v for k,v in wire.items() if k not in ("messages","response_format")})
        self.assertEqual(out["messages"][1],wire["messages"][1])
        schema=out["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertEqual(schema["schema"]["properties"]["drop_ids"]["items"]["enum"],["g8:1:3"])
    def test_bad_decisions_rejected(self):
        for x in [{},{"drop_ids":["x","x"],"reason":"why"},{"drop_ids":[1],"reason":"why"}]:
            with self.assertRaises(ValueError):si.normalize(x)
        self.assertEqual(si.normalize({"drop_ids":["a"],"reason":"why"})["drop"],[{"id":"a","reason":"why"}])
if __name__=="__main__":unittest.main()
