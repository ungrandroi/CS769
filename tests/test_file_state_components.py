import copy,json,unittest
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.cli import counter
from cs769.models.edits import observation_state_components as ed

class FileComponentTests(unittest.TestCase):
    def graph(self,rows):
        h=[{"role":"user","content":"Create and edit the files."}]
        for i,(tool,args,value)in enumerate(rows):
            h.extend([{"type":"function_call","name":tool,"arguments":json.dumps(args),"call_id":str(i)},
                      {"type":"function_call_output","call_id":str(i),"output":json.dumps(value)}])
        return prepare(h,ExperimentConfig(),counter("o200k_base"))["graph"]
    def pair(self,name="a.txt",content="old"):
        return [("touch",{"file_name":name},None),("echo",{"file_name":name,"content":content},None)]
    def test_latest_write_preserves_read_witness_and_original_graph(self):
        rows=self.pair()+[("cat",{"file_name":"a.txt"},{"file_content":"old"}),("echo",{"file_name":"a.txt","content":"new"},None)]
        g=self.graph(rows);before=copy.deepcopy(g);a=ed.pack_files(g)
        self.assertEqual(a["component"]["files_in_creation_order"],[{"name":"a.txt","content":"new"}])
        out,audit,render=ed.apply(g,a,counter("o200k_base"));self.assertEqual(g,before)
        self.assertTrue(audit["retained_evidence_exact"]);self.assertIn("old",render(out))
    def test_distinct_file_identity_and_creation_order(self):
        a=ed.pack_files(self.graph(self.pair("z.txt","z")+self.pair("a.txt","a")))
        self.assertEqual([x["name"]for x in a["component"]["files_in_creation_order"]],["z.txt","a.txt"])
    def test_copy_move_delete_and_cwd_changes_are_barriers(self):
        for tool,args,value in [("cp",{"source":"a.txt","destination":"b.txt"},{"result":"ok"}),("mv",{"source":"a.txt","destination":"b.txt"},{"result":"ok"}),("rm",{"file_name":"a.txt"},None),("cd",{"folder":"missing"},{"error":"missing"})]:
            self.assertIsNone(ed.pack_files(self.graph(self.pair()+[(tool,args,value)])))
    def test_sort_is_a_view_not_a_write(self):
        a=ed.pack_files(self.graph(self.pair(content="z\\na")+[("sort",{"file_name":"a.txt"},{"sorted_content":"a\\nz"})]))
        self.assertEqual(a["component"]["files_in_creation_order"][0]["content"],"z\\na")
    def test_error_and_nonnull_echo_do_not_become_success(self):
        for result in ({"error":"missing"},{"terminal_output":"x"},"broken"):
            self.assertIsNone(ed.pack_files(self.graph([("touch",{"file_name":"a.txt"},None),("echo",{"file_name":"a.txt","content":"x"},result)])))
    def test_bfcl_python_none_serialization_is_success(self):
        from cs769.models.edits.record_edits import evidence
        from cs769.models.edits.relation_pruning import records
        g=self.graph(self.pair());_,cs=records(evidence(g))
        for c in cs:
            for f in c["result"]["fields"]:
                if f["field"]=="output":f["value"]="None"
        self.assertIsNotNone(ed.pack_files(calls=cs))
        for f in cs[-1]["result"]["fields"]:
            if f["field"]=="output":f["value"]="Not a result"
        self.assertIsNone(ed.pack_files(calls=cs))
    def test_terminal_echo_does_not_overwrite_file(self):
        a=ed.pack_files(self.graph(self.pair()+[("echo",{"content":"message"},{"terminal_output":"message"})]))
        self.assertEqual(a["component"]["files_in_creation_order"][0]["content"],"old")
if __name__=="__main__":unittest.main()
