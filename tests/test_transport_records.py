"""Raw replies and billable usage survive failures without automatic retry."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest
import cs769
from cs769.base.budget import PersistentBudget
from cs769.models.http import HTTPTransport, ProviderError
from cs769.models.provider import ProviderTransport
from cs769.base.config import load_config

class TransportRecordTests(unittest.TestCase):
    def test_raw_response_saved_before_usage_validation_failure(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            key = root / "env"
            key.write_text("OPENAI_API_KEY=fixture-only\n")
            key.chmod(0o600)
            budget = PersistentBudget(root / "budget.json", .1, {"input": 1, "output": 1})
            events = []
            http = HTTPTransport("openai", key, budget, authorized=True, record=events.append)
            raw = {"choices": [], "usage": {"prompt_tokens": 10}}
            with patch.dict(os.environ, {"CS769_OFFLINE": "0"}), \
                 patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(raw).encode())) as send:
                with self.assertRaises(ProviderError):
                    http.send({"model": "fixture", "max_tokens": 10, "messages": []})
            self.assertEqual(send.call_count, 1)
            self.assertEqual([x["kind"] for x in events], ["request", "response"])
            self.assertEqual(events[1]["body"], raw)
            ledger = json.loads((root / "budget.json").read_text())
            self.assertEqual(next(iter(ledger["requests"].values()))["status"], "uncertain")
            self.assertNotIn("fixture-only", json.dumps(events))

    def test_raw_response_and_cost_survive_provider_normalization_failure(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            key = root / "env"
            key.write_text("OPENAI_API_KEY=fixture-only\n")
            key.chmod(0o600)
            budget = PersistentBudget(root / "budget.json", .1, {"input": 1, "output": 1})
            events = []
            cfg = load_config(Path(cs769.__file__).parent / "configs/evidence_graph_history_threshold.json")
            transport = ProviderTransport(cfg, HTTPTransport("openai", key, budget, authorized=True, record=events.append))
            raw = {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
            with patch.dict(os.environ, {"CS769_OFFLINE": "0"}), \
                 patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(raw).encode())) as send:
                with self.assertRaises((IndexError, ValueError, KeyError)):
                    transport.send({"input": [{"role": "user", "content": "x"}], "tools": []})
            self.assertEqual(send.call_count, 1)
            self.assertEqual(events[-1]["body"], raw)
            entry = next(iter(json.loads((root / "budget.json").read_text())["requests"].values()))
            self.assertEqual(entry["status"], "settled")
            self.assertAlmostEqual(entry["actual_usd"], .00012)

    def test_invalid_tool_arguments_are_preserved_for_official_evaluation(self):
        from cs769.models.qwen_transport import response_from_chat
        for arguments in ("{broken", "null", "[]"):
            raw = {"model": "fixture", "choices": [{"finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{"id": "c", "type": "function",
                "function": {"name": "du", "arguments": arguments}}]}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
            response = response_from_chat(raw, 0)
            self.assertEqual(response.output[0].arguments, arguments)
            self.assertEqual(response.output[0].name, "du")
