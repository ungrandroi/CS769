"""Counterexamples for witnessed-history edits; no model/API dependency."""
import json
import unittest
from copy import deepcopy
from cs769.cli import counter
from cs769.base.config import ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.models.edits import witness_pruning as wp
from cs769.models.edits.record_edits import evidence


def graph(calls, raw=None):
    h = [{"role":"user","content":"Perform these operations."}]
    if raw is not None:
        h += raw
    else:
        for i,(name,args,result) in enumerate(calls):
            h += [{"type":"function_call","call_id":str(i),"name":name,"arguments":json.dumps(args)},
                  {"type":"function_call_output","call_id":str(i),"output":json.dumps(result)}]
    cfg=ExperimentConfig()
    cfg.delivery={"mode":"replace","role":"assistant"}
    return prepare(h,cfg,counter("o200k_base"))["graph"]


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.count=counter("o200k_base")

    def file_calls(self):
        return [
            ("pwd",{},{"current_working_directory":"/user"}),
            ("find",{"name":"log.txt"},{"matches":["work/log.txt"]}),
            ("cd",{"folder":"work"},{"current_working_directory":"work"}),
            ("mv",{"source":"log.txt","destination":"archive"},{"result":"'log.txt' moved to 'archive/log.txt'"}),
        ]

    def retry_calls(self, mode="START", barrier=None):
        cs=[("startEngine",{"ignitionMode":mode},{"error":"Doors unlocked."}),
            ("lockDoors",{"unlock":False,"door":["driver"]},{"lockStatus":"locked","remainingUnlockedDoors":0}),
            ("pressBrakePedal",{"pedalPosition":1},{"status":"pressed"})]
        if barrier:cs.append(barrier)
        cs += [("startEngine",{"ignitionMode":mode},{"engineState":"running","fuelLevel":40,"batteryVoltage":12}),
               ("post_tweet",{"content":"Ready"},{"id":51,"content":"Ready"})]
        return cs

    def prune(self,g,relations):
        return wp.prune(g,self.count,"Continue the task.",relations=relations,min_saved_tokens=1)

    def unshare(self,g,audit):
        from cs769.models.edits import subtree_share, schema_share
        op=audit["sharing"]["operation"]
        return {"share_subtrees":subtree_share,"share_schema":schema_share}[op].restore(g) if op!="identity" else g

    def test_relocation_retains_move_and_source_graph(self):
        g=graph(self.file_calls());original=deepcopy(g)
        out,audit,render=self.prune(g,["relocated_location"])
        self.assertEqual(g,original)
        self.assertFalse(audit["full_original_evidence_preserved"])
        ev=evidence(self.unshare(out,audit))
        names=[n["fields"][0]["value"] for n in ev["evidence_view"]["nodes"] if n["category"]=="tool_call"]
        self.assertEqual(names,["pwd","cd","mv"])
        self.assertIn("archive/log.txt",render(out))
        self.assertGreater(audit["additional_saved_vs_shared"],0)

    def test_copy_does_not_supersede_source_location(self):
        calls=self.file_calls();calls[-1]=("cp",calls[-1][1],{"result":"'log.txt' copied to 'archive/log.txt'"})
        self.assertFalse(wp.relocation_candidates(graph(calls)))

    def test_distinct_object_failed_move_and_unknown_cwd(self):
        cases=[]
        c=self.file_calls();c[-1]=("mv",{"source":"other.txt","destination":"archive"},{"result":"'other.txt' moved to 'archive/other.txt'"});cases.append(c)
        c=self.file_calls();c[-1]=("mv",c[-1][1],{"error":"Move failed"});cases.append(c)
        cases.append(self.file_calls()[1:])
        for cs in cases:self.assertFalse(wp.relocation_candidates(graph(cs)))

    def test_directory_creation_preserves_existing_file_location(self):
        for result in [None, {"error":"mkdir: File exists"}]:
            cs=self.file_calls();cs.insert(3,("mkdir",{"dir_name":"archive"},result))
            g=graph(cs);out,audit,render=self.prune(g,["relocated_location"])
            self.assertIn("mkdir",render(out))
            self.assertEqual(audit["relation"],"relocated_location")

    def test_unknown_directory_result_is_not_a_reviewed_effect(self):
        cs=self.file_calls();cs.insert(3,("mkdir",{"dir_name":"archive"},{"unexpected":"state"}))
        self.assertFalse(wp.relocation_candidates(graph(cs)))

    def test_unknown_mutation_invalidates_old_observation(self):
        cs=self.file_calls();cs.insert(2,("unknown_write",{},{"success":True}))
        self.assertFalse(wp.relocation_candidates(graph(cs)))

    def test_other_matches_or_fields_are_not_silently_dropped(self):
        for result in [{"matches":["work/log.txt","other/log.txt"]},
                       {"matches":["work/log.txt"],"uncovered":"keep"},
                       ["work/log.txt"]]:
            cs=self.file_calls();cs[1]=("find",cs[1][1],result)
            self.assertFalse(wp.relocation_candidates(graph(cs)))

    def test_historical_request_preserves_observation(self):
        with self.assertRaises(ValueError):
            wp.prune(graph(self.file_calls()),self.count,"Where was the file originally?",min_saved_tokens=1)

    def test_retry_preserves_success_prerequisites_and_post_id(self):
        g=graph(self.retry_calls());original=deepcopy(g)
        out,audit,render=self.prune(g,["resolved_error"])
        self.assertEqual(g,original)
        self.assertEqual(audit["relation"],"resolved_error")
        text=render(out)
        self.assertNotIn("Doors unlocked.",text)
        self.assertIn("post_tweet",text);self.assertIn("51",text)
        self.assertIn("lockDoors",text);self.assertIn("pressBrakePedal",text)

    def test_stop_error_may_have_side_effects_and_is_not_supported(self):
        with self.assertRaises(ValueError):
            self.prune(graph(self.retry_calls("STOP")),["resolved_error"])

    def test_unknown_scope_change_blocks_retry_deletion(self):
        with self.assertRaises(ValueError):
            self.prune(graph(self.retry_calls(barrier=("message_login",{"user_id":"other"},{"success":True}))),["resolved_error"])

    def test_parallel_outcomes_are_not_a_serial_retry(self):
        raw=[
            {"type":"function_call","call_id":"a","name":"startEngine","arguments":'{"ignitionMode":"START"}'},
            {"type":"function_call","call_id":"b","name":"startEngine","arguments":'{"ignitionMode":"START"}'},
            {"type":"function_call_output","call_id":"a","output":'{"error":"Not ready"}'},
            {"type":"function_call_output","call_id":"b","output":'{"engineState":"running"}'},
        ]
        with self.assertRaises(ValueError):self.prune(graph([],raw),["resolved_error"])

    def test_relation_can_be_disabled(self):
        with self.assertRaises(ValueError):self.prune(graph(self.file_calls()),["resolved_error"])



class RetryContractTests(unittest.TestCase):
    def setUp(self):
        self.count = counter("o200k_base")

    def file(self):
        return [
            ("cat", {"file_name": "x.txt"}, {"error": "cat: 'x.txt': No such file or directory"}),
            ("touch", {"file_name": "x.txt"}, None),
            ("cat", {"file_name": "x.txt"}, {"file_content": ""}),
        ]

    def send(self):
        return [
            ("send_message", {"receiver_id": "u2", "message": "Keep these exact words."},
             {"error": "No user is currently logged in."}),
            ("message_get_login_status", {}, {"login_status": False}),
            ("get_user_id", {"user": "Alice"}, {"user_id": "u1"}),
            ("message_login", {"user_id": "u1"}, {"login_status": True}),
            ("send_message", {"receiver_id": "u2", "message": "Keep these exact words."},
             {"sent_status": True, "message_id": {"new_id": 91}, "message": "sent"}),
        ]

    def run_edit(self, cs, contract, current="Continue the task.", raw=None):
        return wp.prune(graph(cs, raw), self.count, current, relations=["resolved_error"],
                        resolved_contracts=[contract], min_saved_tokens=1)

    def reject(self, cs, contract):
        with self.assertRaises(ValueError):
            self.run_edit(cs, contract)

    def test_created_file_preserves_repair_and_empty_success(self):
        original = graph(self.file())
        before = deepcopy(original)
        out, audit, render = wp.prune(original, self.count, "Continue.",
            relations=["resolved_error"], resolved_contracts=["created_file"], min_saved_tokens=1)
        self.assertEqual(original, before)
        self.assertIn("touch", render(out))
        self.assertIn("file_content", render(out))
        self.assertNotIn("No such file or directory", render(out))
        self.assertEqual(len(audit["edit"]["action"]["removed_event_ids"]), 2)
        self.assertFalse(audit["full_original_evidence_preserved"])

    def test_extension_is_not_enabled_by_default(self):
        for cs in [self.file(), self.send()]:
            with self.assertRaises(ValueError):
                wp.prune(graph(cs), self.count, "Continue.",
                         relations=["resolved_error"], min_saved_tokens=1)

    def test_file_scope_change_even_if_cd_failed_is_rejected(self):
        for result in [{"current_working_directory": "other"}, {"error": "not found"}]:
            cs = self.file()
            cs.insert(1, ("cd", {"folder": "other"}, result))
            self.reject(cs, "created_file")

    def test_unknown_mutation_or_different_created_file_rejected(self):
        cs = self.file()
        cs.insert(1, ("unknown_write", {}, {"success": True}))
        self.reject(cs, "created_file")
        cs = self.file()
        cs[1] = ("touch", {"file_name": "y.txt"}, None)
        self.reject(cs, "created_file")

    def test_failed_or_ambiguous_creation_does_not_witness_repair(self):
        for value in [{"error": "exists"}, {}, {"success": True}]:
            cs = self.file()
            cs[1] = ("touch", {"file_name": "x.txt"}, value)
            self.reject(cs, "created_file")

    def test_file_read_not_directory_or_permission_errors(self):
        cs = self.file()
        cs[0] = ("cat", {"file_name": "x.txt"}, {"error": "Permission denied"})
        self.reject(cs, "created_file")

    def test_login_preserves_sender_receiver_payload_and_receipt(self):
        out, audit, render = self.run_edit(self.send(), "authenticated_send")
        for value in ["message_login", "u1", "u2", "Keep these exact words.", "91"]:
            self.assertIn(value, render(out))
        self.assertNotIn("No user is currently logged in.", render(out))
        self.assertEqual(len(audit["edit"]["action"]["removed_event_ids"]), 2)

    def test_login_must_succeed_and_be_unique(self):
        cs = self.send()
        cs[3] = ("message_login", {"user_id": "u1"}, {"login_status": False})
        self.reject(cs, "authenticated_send")
        cs = self.send()
        cs.insert(4, ("message_login", {"user_id": "other"}, {"login_status": True}))
        self.reject(cs, "authenticated_send")

    def test_logout_unknown_call_or_intervening_send_blocks_removal(self):
        for barrier in [("message_logout", {}, {"success": True}),
                        ("unknown_auth", {}, {"success": True}),
                        ("send_message", {"receiver_id": "u3", "message": "Other"},
                         {"sent_status": True, "message_id": 92})]:
            cs = self.send()
            cs.insert(4, barrier)
            self.reject(cs, "authenticated_send")

    def test_different_payload_or_receiver_is_not_a_retry(self):
        for key, value in [("receiver_id", "u3"), ("message", "Changed text")]:
            cs = self.send()
            name, args, result = cs[-1]
            cs[-1] = (name, dict(args, **{key: value}), result)
            self.reject(cs, "authenticated_send")

    def test_unknown_send_error_or_unsuccessful_receipt_is_not_eligible(self):
        cs = self.send()
        cs[0] = (cs[0][0], cs[0][1], {"error": "Network failure; may have sent"})
        self.reject(cs, "authenticated_send")
        cs = self.send()
        cs[-1] = (cs[-1][0], cs[-1][1], {"sent_status": False, "message_id": 91})
        self.reject(cs, "authenticated_send")

    def test_parallel_repair_and_retry_are_rejected(self):
        raw = [
            {"role": "user", "content": "Read the file."},
            {"type": "function_call", "call_id": "a", "name": "cat", "arguments": '{"file_name":"x.txt"}'},
            {"type": "function_call_output", "call_id": "a", "output": json.dumps({"error":"cat: 'x.txt': No such file or directory"})},
            {"type": "function_call", "call_id": "b", "name": "touch", "arguments": '{"file_name":"x.txt"}'},
            {"type": "function_call", "call_id": "c", "name": "cat", "arguments": '{"file_name":"x.txt"}'},
            {"type": "function_call_output", "call_id": "b", "output": "null"},
            {"type": "function_call_output", "call_id": "c", "output": '{"file_content":""}'},
        ]
        with self.assertRaises(ValueError):
            self.run_edit([], "created_file", raw=raw)

    def test_error_explanation_request_keeps_failed_attempt(self):
        with self.assertRaises(ValueError):
            self.run_edit(self.send(), "authenticated_send", "Why did the message fail?")

    def test_cross_episode_success_does_not_erase_old_failure(self):
        raw = []
        for i, (name, args, value) in enumerate(self.file()):
            if i == 1:
                raw.append({"role": "user", "content": "New separate task."})
            raw.extend([
                {"type": "function_call", "call_id": str(i), "name": name, "arguments": json.dumps(args)},
                {"type": "function_call_output", "call_id": str(i), "output": json.dumps(value)},
            ])
        with self.assertRaises(ValueError):
            self.run_edit([], "created_file", raw=raw)




class LocatedReadTests(unittest.TestCase):
    def setUp(self):
        self.count = counter("o200k_base")

    def calls(self):
        return [
            ("find", {"name": "x.txt"}, {"matches": ["./docs/x.txt"]}),
            ("cat", {"file_name": "x.txt"}, {"error": "cat: 'x.txt': No such file or directory"}),
            ("cd", {"folder": "docs"}, {"current_working_directory": "docs"}),
            ("cat", {"file_name": "x.txt"}, {"file_content": "Exact retained evidence."}),
        ]

    def edit(self, calls=None, raw=None, current="Send its contents verbatim."):
        return wp.prune(graph(self.calls() if calls is None else calls, raw),
            self.count, current, relations=["resolved_error"],
            resolved_contracts=["located_read"], min_saved_tokens=1)

    def reject(self, calls):
        with self.assertRaises(ValueError):self.edit(calls)

    def test_retained_content_paths_and_source_unchanged(self):
        g=graph(self.calls());before=deepcopy(g)
        out,audit,render=wp.prune(g,self.count,"Send its contents verbatim.",
            relations=["resolved_error"],resolved_contracts=["located_read"],min_saved_tokens=1)
        self.assertEqual(g,before)
        for value in ["find","docs","cd","Exact retained evidence."]:self.assertIn(value,render(out))
        self.assertNotIn("No such file or directory",render(out))
        self.assertEqual(len(audit["edit"]["action"]["removed_event_ids"]),2)
        proof=audit["edit"]["located_read_proofs"][0]
        self.assertNotEqual(proof["failed_path_relative_to_find_scope"],proof["successful_path_relative_to_find_scope"])
        self.assertFalse(proof["same_object_asserted"])
        self.assertEqual(audit["version"],"g9-witness-pruning-v1.2")

    def test_disabled_in_default_and_prior_extension(self):
        for contracts in [None,["created_file","authenticated_send"]]:
            kw={} if contracts is None else {"resolved_contracts":contracts}
            with self.assertRaises(ValueError):
                wp.prune(graph(self.calls()),self.count,"Continue.",
                    relations=["resolved_error"],min_saved_tokens=1,**kw)

    def test_ambiguous_match_missing_match_or_extra_fields(self):
        for value in [{"matches":["./docs/x.txt","./else/x.txt"]},{"matches":[]},
                      {"matches":["./docs/x.txt"],"extra":1}]:
            cs=self.calls();cs[0]=("find",cs[0][1],value);self.reject(cs)

    def test_path_ambiguity_and_different_target(self):
        for path in ["/docs/x.txt","docs/x.txt","./../x.txt","./docs/../x.txt",
                     "./a/b/x.txt","./x.txt","./docs/y.txt",".//x.txt"]:
            cs=self.calls();cs[0]=("find",cs[0][1],{"matches":[path]});self.reject(cs)

    def test_other_find_scope_or_later_ambiguous_find(self):
        cs=self.calls();cs[0]=("find",{"name":"x.txt","path":"other"},cs[0][2]);self.reject(cs)
        cs=self.calls();cs.insert(1,("find",{"name":"x.txt"},{"matches":[]}));self.reject(cs)

    def test_directory_receipt_must_match(self):
        for args,value in [({"folder":"other"},{"current_working_directory":"other"}),
                           ({"folder":"docs"},{"error":"not found"}),
                           ({"folder":"docs"},{"current_working_directory":"other"}),
                           ({"folder":"docs"},{})]:
            cs=self.calls();cs[2]=("cd",args,value);self.reject(cs)

    def test_writes_unknown_calls_and_extra_cd(self):
        for barrier in [("touch",{"file_name":"z"},None),("unknown",{},{"ok":True}),("cd",{"folder":".."},{})]:
            for index in [1,2,3]:
                cs=self.calls();cs.insert(index,barrier);self.reject(cs)

    def test_missing_find_or_unsuccessful_read(self):
        self.reject(self.calls()[1:])
        for value in [{"error":"missing"},{"file_content":"ok","extra":1}]:
            cs=self.calls();cs[-1]=("cat",{"file_name":"x.txt"},value);self.reject(cs)

    def test_other_error_and_changed_arguments(self):
        cs=self.calls();cs[1]=("cat",cs[1][1],{"error":"Permission denied"});self.reject(cs)
        cs=self.calls();cs[-1]=("cat",{"file_name":"y.txt"},{"file_content":"different"});self.reject(cs)

    def test_reads_can_interleave(self):
        cs=self.calls();cs.insert(1,("ls",{},{"current_directory_content":["docs"]}))
        cs.insert(4,("ls",{},{"current_directory_content":["x.txt"]}));self.edit(cs)

    def raw(self):
        raw=[]
        for i,(name,args,value) in enumerate(self.calls()):
            raw.extend([{"type":"function_call","call_id":str(i),"name":name,"arguments":json.dumps(args)},
                        {"type":"function_call_output","call_id":str(i),"output":json.dumps(value)}])
        return raw

    def test_parallel_anchor_and_repair_rejected(self):
        for i,j in [(1,2),(5,6)]:
            raw=self.raw();raw[i],raw[j]=raw[j],raw[i]
            with self.assertRaises(ValueError):self.edit([],raw=raw)

    def test_find_may_be_prior_turn_but_retry_same_turn(self):
        raw=self.raw();raw.insert(2,{"role":"user","content":"Read it."})
        self.edit([],raw=raw)
        raw.insert(-2,{"role":"user","content":"Now read again."})
        with self.assertRaises(ValueError):self.edit([],raw=raw)

    def test_historical_error_questions_block_removal(self):
        for text in ["Why did reading fail?","Where was it originally?","Describe the error."]:
            with self.assertRaises(ValueError):self.edit(current=text)

if __name__=="__main__":
    unittest.main()
