import unittest
from copy import deepcopy
from cs769.tasks.campaign import unreviewed_regressions

class ReviewGateTests(unittest.TestCase):
    def test_review_does_not_remove_reported_loss(self):
        losses=[{"task":"case106","baseline":"identity"}]
        before=deepcopy(losses)
        self.assertEqual(unreviewed_regressions(losses,[{"task":"case106","baseline":"identity","decision":"continue"}]),[])
        self.assertEqual(losses,before)

    def test_new_task_or_baseline_still_stops(self):
        old={"task":"case106","baseline":"identity"}
        new=[{"task":"case112","baseline":"identity"},{"task":"case112","baseline":"g9_full"},{"task":"case106","baseline":"g9_full"}]
        self.assertEqual(unreviewed_regressions([old,*new],[{**old,"decision":"continue"}]),new)

    def test_no_review_and_invalid_review_fail_closed(self):
        losses=[{"task":"case106","baseline":"identity"}]
        self.assertEqual(unreviewed_regressions(losses,[]),losses)
        with self.assertRaises(ValueError):
            unreviewed_regressions(losses,[{"task":"case106","baseline":"identity"}])

if __name__=="__main__":unittest.main()
