"""Sampling assertions run through current configuration and provider formatting."""
from pathlib import Path
import unittest
import cs769
from cs769.base.config import load_config, ExperimentConfig
from cs769.tasks.memory import prepare
from cs769.base.requests import build_request
from cs769.models.provider import openai_body

CONFIGS = Path(cs769.__file__).parent / "configs"

class RequestParameterTests(unittest.TestCase):
    def test_current_default_and_explicit_sampling_reach_the_wire(self):
        cfg = load_config(CONFIGS / "evidence_graph_history_threshold.json")
        self.assertEqual(openai_body({"input": [{"role": "user", "content": "x"}]}, cfg.model)["seed"], 42)
        data = cfg.to_dict()
        data["model"]["sampling"] = {"seed": 43, "temperature": .7, "max_tokens": 4096}
        cfg = ExperimentConfig.from_dict(data)
        wire = build_request(prepare([{"role": "user", "content": "x"}], cfg, len), [])
        self.assertEqual(wire["seed"], 43)
        self.assertEqual(wire["temperature"], .7)
        self.assertEqual(wire["max_tokens"], 4096)

    def test_reasoning_sampling_is_forwarded_without_temperature(self):
        cfg = load_config(CONFIGS / "evidence_graph_openai_mini.json")
        wire = openai_body({"input": [{"role": "user", "content": "x"}]}, cfg.model)
        self.assertNotIn("temperature", wire)
        self.assertEqual(wire["reasoning_effort"], cfg.model["sampling"]["reasoning_effort"])
        self.assertEqual(wire["max_completion_tokens"], 16384)

    def test_invalid_reasoning_temperature_and_nonfinite_values_are_rejected(self):
        for value in (0, .7, 1):
            data = load_config(CONFIGS / "evidence_graph_openai_mini.json").to_dict()
            data["model"]["sampling"]["temperature"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExperimentConfig.from_dict(data)
        for value in (float("nan"), float("inf"), -1, 3):
            data = load_config(CONFIGS / "evidence_graph_history_threshold.json").to_dict()
            data["model"]["sampling"]["temperature"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExperimentConfig.from_dict(data)

    def test_repeat_metadata_is_not_an_anthropic_seed(self):
        cfg = ExperimentConfig()
        cfg.model = {"provider": "anthropic", "name": "fixture", "old_thinking": "omit", "sampling": {"max_tokens": 100}}
        wire = build_request(prepare([{"role": "user", "content": "x"}], cfg, len), [])
        self.assertNotIn("seed", wire)
        cfg.model["sampling"]["seed"] = 42
        with self.assertRaises(ValueError):
            build_request(prepare([{"role": "user", "content": "x"}], cfg, len), [])
