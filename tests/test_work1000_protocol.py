"""Tests of branch eligibility and sampling, without model inference."""
import unittest
from workflows.work1000_task import all_paired, request_body, SAMPLING, validate_source


class WorkingProtocolTests(unittest.TestCase):
    def test_no_minimum_call_or_future_filter(self):
        self.assertTrue(all_paired([{'role':'user','content':'long task'}]))
        self.assertFalse(all_paired([{'type':'function_call','call_id':'x'}]))
        self.assertTrue(all_paired([{'type':'function_call','call_id':'x'},
                                    {'type':'function_call_output','call_id':'x','output':'ok'}]))

    def test_all_parallel_results_required(self):
        self.assertFalse(all_paired([{'type':'function_call','call_id':'x'},
                                     {'type':'function_call','call_id':'y'},
                                     {'type':'function_call_output','call_id':'x'}]))

    def test_reject_duplicate_and_out_of_order_ids(self):
        call = {'type': 'function_call', 'call_id': 'x'}
        result = {'type': 'function_call_output', 'call_id': 'x'}
        for history in ([call, call, result], [call, result, result],
                        [result, call], [call, result, call, result],
                        [{'type': 'function_call'}]):
            self.assertFalse(all_paired(history))

    def test_source_configuration_must_match(self):
        source = dict(method='identity', status='complete', task='task',
                      category='category', seed=1103, sampling=SAMPLING,
                      threshold=1000,
                      threshold_metric='native full minus fixed-only template tokens',
                      context=131072, max_tokens=4096)
        validate_source(source, 'task', 'category', 1103)
        for key in ('task', 'category', 'sampling', 'seed', 'threshold'):
            changed = dict(source, **{key: None})
            with self.assertRaisesRegex(AssertionError, key):
                validate_source(changed, 'task', 'category', 1103)

    def test_live_sampling_is_nondeterministic_and_identical_across_methods(self):
        req={'input':[{'role':'user','content':'hello'}], 'tools':[]}
        native=request_body(req,2207)
        self.assertEqual(native['seed'],2207)
        for key,value in SAMPLING.items():self.assertEqual(native[key],value)
        self.assertGreater(native['temperature'],0)
        self.assertFalse(native['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(native['max_tokens'],4096)


if __name__=='__main__':unittest.main()
