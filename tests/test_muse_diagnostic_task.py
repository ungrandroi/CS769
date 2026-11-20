"""Muse-specific source/profile/native-boundary controls, without inference."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from core import lossless_event, lossless_state, optimized_graph
from core.diagnostic_views import goal_boundary_views
from workflows.muse_diagnostic_task import (ARMS, METHODS, MUSE_USER_BOUNDARY,
                                            prepare_replacement, validate_muse_pair,
                                            validate_runtime_contract)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/bfcl_identity/muse_transfer_v1"
MODEL = "Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL"
MODEL_KEY = "local/Muse-Glimmer-30B-Q4-K-XL-FC"
POLICY = "generate_low; raw_reasoning_logged; historical_reasoning_not_reinserted"


def manifests():
    identity = {"model": MODEL, "model_key": MODEL_KEY, "reasoning_policy": POLICY,
                "semantics": "mixed"}
    return identity, deepcopy(identity)


def test_muse_source_pair_requires_own_model_reasoning_and_semantics():
    identity, graph = manifests()
    validate_muse_pair(identity, graph, MODEL, MODEL_KEY, POLICY)
    for field, wrong in [("model", "Qwen3.8-27B"), ("model_key", "local/Qwen-FC"),
                         ("reasoning_policy", "no_thinking"), ("semantics", "unknown")]:
        changed = deepcopy(identity)
        changed[field] = wrong
        with pytest.raises(AssertionError):
            validate_muse_pair(changed, graph, MODEL, MODEL_KEY, POLICY)
    graph["semantics"] = "filesystem"
    with pytest.raises(AssertionError, match="different semantic"):
        validate_muse_pair(identity, graph, MODEL, MODEL_KEY, POLICY)


def contract_fixture():
    projection = {"model_alias": "bfcl-muse-glimmer-30b", "chat_template": "server-native-template",
                  "default_generation_settings": {"n_ctx": 131072}, "model_path": "/models/muse.gguf"}
    contract = {"props_projection": projection, "props_projection_keys": list(projection),
                "chat_template_sha256": hashlib.sha256(projection["chat_template"].encode()).hexdigest(),
                "rendered_tokenization": {"add_special": True, "parse_special": True},
                "plain_tokenization": {"add_special": False, "parse_special": False},
                "reasoning_strength": "low", "request_max_tokens": 16384}
    return deepcopy(projection), contract


def test_runtime_contract_pins_serving_template_and_muse_bos_policy():
    props, contract = contract_fixture()
    validate_runtime_contract(props, contract, "bfcl-muse-glimmer-30b")
    changed = deepcopy(props)
    changed["chat_template"] = "raw GGUF template is not the serving template"
    with pytest.raises(AssertionError, match="template changed"):
        validate_runtime_contract(changed, contract, "bfcl-muse-glimmer-30b")
    changed = deepcopy(contract)
    changed["rendered_tokenization"]["add_special"] = False
    with pytest.raises(AssertionError, match="rendered-token"):
        validate_runtime_contract(props, changed, "bfcl-muse-glimmer-30b")
    changed = deepcopy(props)
    changed["default_generation_settings"]["n_ctx"] = 16384
    with pytest.raises(AssertionError, match="default_generation"):
        validate_runtime_contract(changed, contract, "bfcl-muse-glimmer-30b")


def test_runtime_contract_distinguishes_old_source_and_live_output_budgets():
    props, contract = contract_fixture()
    old_contract = deepcopy(contract)
    old_contract["request_max_tokens"] = 4096
    with pytest.raises(AssertionError, match="output budget"):
        validate_runtime_contract(props, old_contract, "bfcl-muse-glimmer-30b")
    validate_runtime_contract(props, old_contract, "bfcl-muse-glimmer-30b", 4096)
    validate_runtime_contract(props, contract, "bfcl-muse-glimmer-30b", 16384)


@pytest.mark.parametrize("method", METHODS)
def test_archived_muse_own_graph_all_six_arms(method):
    seed = SOURCE / "evaluation/multi_turn_long_context_37/seed4409"
    graph_path = seed / (method + "-optimized") / "memory-metadata.json"
    if not graph_path.exists():
        pytest.skip("Frozen Muse pilot unavailable")
    source = json.loads(graph_path.read_text())
    history = json.loads((seed / "identity/checkpoint-history.json").read_text())
    codec = lossless_state if method == "state" else lossless_event
    outputs = {}
    for arm in ARMS:
        messages, meta = prepare_replacement(history, source, method, arm, len)
        assert optimized_graph._same(codec.decode(meta["encoded"]), source["graph"])
        assert meta["instruction"] == optimized_graph.MINIMAL
        assert meta["adapter_rebuilt"] is False
        outputs[arm] = messages
    assert outputs["goal_inline"][0]["content"] == "".join(
        message["content"] for message in outputs["goal_separate"])
    if method in ("event", "dedup"):
        # Legacy pure-filesystem payloads lack fact_scope. They remain a valid
        # zero-index negative control, never silently rebuilt with new labels.
        assert "fact_scope" not in source["graph"]["fact_columns"]
        assert outputs["index_control"] == outputs["index_view"]
    if method == "event":
        assert outputs["refs_control"] == outputs["refs_expanded"]


def test_exact_muse_serving_template_user_boundary_when_renderer_available():
    pytest.importorskip("transformers")
    from transformers.utils.chat_template_utils import _compile_jinja_template
    contract_path = SOURCE / "runtime/runtime-contract.json"
    if not contract_path.exists():
        pytest.skip("Frozen Muse serving-template contract unavailable")
    contract = json.loads(contract_path.read_text())
    props = contract["props_projection"]
    validate_runtime_contract(props, contract, "bfcl-muse-glimmer-30b", contract["request_max_tokens"])
    template = _compile_jinja_template(props["chat_template"])
    memory = '{"memory":"unchanged"}'
    goal = '\n Move "报告.txt". Keep completed actions. \n'
    pair = goal_boundary_views([{"role": "user", "content": memory}], goal)
    def render(messages):
        return template.render(messages=[{"role": "system", "content": "fixed"}, *messages], tools=[],
                               reasoning_strength="low", preserve_thinking=False,
                               add_generation_prompt=True, bos_token="", eos_token=props["eos_token"])
    inline, separate = render(pair["inline"]), render(pair["separate"])
    assert separate == inline.replace(memory + pair["goal_view"],
                                      memory + MUSE_USER_BOUNDARY + pair["goal_view"], 1)
    assert pair["goal_view"] in inline and pair["goal_view"] in separate
    assert "<|im_start|>" not in separate
    assert not separate.startswith(props["bos_token"])


def test_muse_runner_refuses_nonempty_attempt_before_runtime_imports(tmp_path):
    from workflows.muse_diagnostic_task import main
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="Never overwrite"):
        main(["--task", "x", "--category", "x", "--seed", "1", "--method", "state", "--arm", "goal_inline",
              "--identity", "unused", "--source-graph", "unused", "--output", str(tmp_path)])
