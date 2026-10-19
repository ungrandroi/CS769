import unittest
from audit_history_checkpoints import first_checkpoint
class CheckpointsTest(unittest.TestCase):
    def test_single_call_final_request_is_eligible(self):
        h=[{'type':'function_call','call_id':'a','name':'cat','arguments':'{}'},{'type':'function_call_output','call_id':'a','output':'x'*1000}]
        tape=[{'request':{'input':h},'response':{'usage':{'input_tokens':2000}}}]
        self.assertEqual(first_checkpoint(tape,len)['trigger_index'],0)
    def test_tools_and_user_text_do_not_trigger(self):
        tape=[{'request':{'input':[{'role':'user','content':'x'*5000}],'tools':['x'*5000]},'response':{'usage':{'input_tokens':10000}}}]
        self.assertIsNone(first_checkpoint(tape,len))
    def test_unpaired_call_does_not_trigger(self):
        h=[{'type':'function_call','call_id':'a','name':'cat','arguments':'x'*2000}]
        self.assertIsNone(first_checkpoint([{'request':{'input':h}}],len))
if __name__=='__main__':unittest.main()
