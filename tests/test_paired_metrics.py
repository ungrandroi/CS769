"""Generic paired reporting replaces tests tied to old fixed task lists."""
import unittest
from cs769.base.metrics import paired, Usage, cost_from_usage
from cs769.base.schedule import schedule

def row(task, arm, passed, repeat=1, calls=1):
    return {"task": task, "checkpoint_sha256": "same", "repeat": repeat, "arm": arm,
            "passed": passed, "usage": {"tool_calls": calls, "first_input_tokens": 100, "total_tokens": 200}}

class PairedMetricsTests(unittest.TestCase):
    def test_zero_denominator_is_unknown_not_success(self):
        result = paired([])
        self.assertEqual(result["paired_samples"], 0)
        self.assertIsNone(result["baseline_rate"])
        self.assertIsNone(result["candidate_rate"])
        self.assertIsNone(result["delta_pp"])

    def test_equal_totals_do_not_hide_losses_and_gains(self):
        result = paired([row("loss", "identity", True), row("loss", "g9", False),
                         row("gain", "identity", False), row("gain", "g9", True)])
        self.assertEqual(result["delta_pp"], 0)
        self.assertEqual(result["regressions"], ["loss"])
        self.assertEqual(result["gains"], ["gain"])

    def test_later_repeat_does_not_erase_an_earlier_loss(self):
        result = paired([row("x", "identity", True), row("x", "g9", False),
                         row("x", "identity", False, repeat=2), row("x", "g9", True, repeat=2)])
        self.assertEqual(result["paired_samples"], 2)
        self.assertEqual(result["regressions"], ["x"])
        self.assertEqual(result["gains"], ["x"])

    def test_incomplete_pairs_are_excluded_and_duplicates_rejected(self):
        rows = [row("complete", "identity", True), row("complete", "g9", True),
                row("incomplete", "identity", False)]
        result = paired(rows)
        self.assertEqual(result["paired_samples"], 1)
        self.assertEqual(result["unpaired_conditions"], 1)
        self.assertEqual(result["baseline_rate"], 1)
        with self.assertRaises(ValueError):
            paired(rows + [rows[0]])

    def test_different_checkpoints_and_nonbinary_scores_cannot_form_a_pair(self):
        a = row("x", "identity", True)
        b = row("x", "g9", True)
        b["checkpoint_sha256"] = "different"
        self.assertEqual(paired([a, b])["paired_samples"], 0)
        a["passed"] = "error"
        with self.assertRaises(ValueError):
            paired([a, b])

    def test_tool_call_increase_is_reported_both_net_and_positive(self):
        result = paired([row("x", "identity", True, calls=1), row("x", "g9", True, calls=4),
                         row("y", "identity", True, calls=4), row("y", "g9", True, calls=2)])
        self.assertEqual(result["baseline_tool_calls"], 5)
        self.assertEqual(result["candidate_tool_calls"], 6)
        self.assertEqual(result["net_added_tool_calls"], 1)
        self.assertEqual(result["positive_added_tool_calls"], 3)

    def test_cache_and_reasoning_are_subsets_not_extra_tokens(self):
        packet = {"choices": [{"message": {"tool_calls": [{"id": "c"}]}}],
                  "usage": {"prompt_tokens": 200, "completion_tokens": 20,
                            "prompt_tokens_details": {"cached_tokens": 80},
                            "completion_tokens_details": {"reasoning_tokens": 12}}}
        usage = Usage()
        usage.add(packet, "openai")
        self.assertEqual(usage.report()["total_tokens"], 220)
        self.assertEqual(usage.tool_calls, 1)
        self.assertEqual(usage.first_input_tokens, 200)
        self.assertEqual(usage.cached_input_tokens, 80)
        rates = {"input": 2, "cached_input": .5, "output": 8, "cache_write": 2}
        self.assertAlmostEqual(cost_from_usage(usage, rates), (120 * 2 + 80 * .5 + 20 * 8) / 1e6)

    def test_explicit_plan_is_reproducible_and_each_repeat_is_distinct(self):
        jobs = schedule(["x", "y"], ["identity", "g9"], repeats=3, seed=42)
        self.assertEqual(jobs, schedule(["x", "y"], ["identity", "g9"], repeats=3, seed=42))
        self.assertNotEqual(jobs, schedule(["x", "y"], ["identity", "g9"], repeats=3, seed=43))
        self.assertEqual(len(jobs), 12)
        self.assertEqual(len({(x["task"], x["arm"], x["repeat"]) for x in jobs}), 12)
        with self.assertRaises(ValueError):
            schedule(["x", "x"], ["identity", "g9"])
