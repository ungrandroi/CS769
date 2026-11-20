import unittest
from copy import deepcopy
from test_relation_pruning import graph
from cs769.models.edits import booking_receipt as br, relation_pruning as rp
from cs769.cli import counter

class BookingReceiptTests(unittest.TestCase):
    def setUp(self):
        self.count = counter("o200k_base")
        self.route = dict(travel_from="AAA", travel_to="BBB", travel_date="2026-01-01", travel_class="economy")
        self.quote = ("get_flight_cost", self.route, {"travel_cost_list": list(range(100,400)) + [150]})
        self.receipt = {"booking_status": True, "booking_id":"b", "transaction_id":"t",
                        "booking_history":{"b":dict(self.route, transaction_id="t", travel_cost=150)}}
    def calls(self, receipt=None, route=None):
        return [deepcopy(self.quote), ("book_flight", deepcopy(route or self.route), deepcopy(self.receipt if receipt is None else receipt))]
    def eligible(self, calls, current="Get invoice for the booking."):
        return br.candidates(graph(calls), current)[0]
    def test_keep_receipt_and_all_duplicate_or_reused_values(self):
        calls=self.calls()+[("compute_exchange_rate", {"value":210}, {"exchanged_value":200})]
        g=graph(calls); before=deepcopy(g)
        out,audit=br.prune(g,self.count,"Get invoice.")
        ns,_=rp.records(rp.evidence(out)); old,_=rp.records(rp.evidence(g))
        target=audit["action"]["source_result"]
        for a,b in zip(old,ns):
            if a["id"] != target: self.assertEqual(a,b)
        v=next(rp.load(rp.fields(n)["output"]) for n in ns if n["id"]==target)
        self.assertEqual(v["travel_cost_list"],[150,210,150])
        self.assertEqual(g,before); self.assertFalse(audit["causal_dependency_proven"])
        self.assertFalse(audit["full_original_evidence_preserved"])
        self.assertIn("matching booking receipt",br.render(out))
        self.assertNotIn("operands were used",br.render(out))
    def test_wrong_route_and_failed_or_incomplete_receipt_rejected(self):
        self.assertFalse(self.eligible(self.calls(route=dict(self.route,travel_to="CCC"))))
        for mutate in [
            lambda r:r.update(booking_status=False), lambda r:r.update(booking_status=1),
            lambda r:r.pop("booking_id"), lambda r:r.pop("transaction_id"),
            lambda r:r.update(booking_history={}),
            lambda r:r["booking_history"]["b"].update(travel_cost=99999),
            lambda r:r["booking_history"]["b"].update(transaction_id="x"),
            lambda r:r["booking_history"]["b"].update(travel_to="CCC")]:
            r=deepcopy(self.receipt); mutate(r)
            self.assertFalse(self.eligible(self.calls(receipt=r)))
    def test_ambiguous_quote_cancel_requote_rebook_and_auth_rejected(self):
        variants=[
            [deepcopy(self.quote)]+self.calls(),
            self.calls()+[("cancel_booking",{"booking_id":"b"},{"status":"success"})],
            self.calls()+[deepcopy(self.quote)],
            self.calls()+[self.calls()[-1]],
            [deepcopy(self.quote),("login",{},{"access_token":"x"}),self.calls()[-1]]]
        for calls in variants: self.assertFalse(self.eligible(calls))
    def test_failed_cancellation_not_success_witness(self):
        self.assertTrue(self.eligible(self.calls()+[("cancel_booking",{"booking_id":"b"},{"error":"failed"})]))
    def test_history_request_and_stale_action(self):
        self.assertFalse(self.eligible(self.calls(),"Compare the previous quotes."))
        g=graph(self.calls()); a=br.candidates(g,"Get invoice.")[0][0]
        other=graph(self.calls()+[("retrieve_invoice",{"booking_id":"b"},{"invoice_id":"i"})])
        with self.assertRaisesRegex(ValueError,"Stale"):br.apply(other,a,self.count)
    def test_no_implicit_old_consumed_change(self):
        self.assertFalse(rp.candidates(graph(self.calls()),"Get invoice.","consumed")[0])
        self.assertTrue(br.candidates(graph(self.calls()),"Get invoice.")[0])
    def test_minimum_saving(self):
        with self.assertRaisesRegex(ValueError,"No eligible"):
            br.prune(graph(self.calls()),self.count,"Get invoice.",min_saved_tokens=100000)
if __name__ == "__main__":unittest.main()
