"""Live output budgets must preserve history and reserve the same context space."""
from copy import deepcopy
import json

import pytest

from core.generation_budget import (DEFAULT_MAX_OUTPUT_TOKENS, fits_context,
                                    request_with_output_budget, validate_max_output_tokens)


def test_live_override_keeps_historical_factory_and_input_unchanged():
    historical = {"max_tokens": 4096, "input": [{"role": "user", "content": "same goal"}]}
    original = deepcopy(historical)
    native = {"max_tokens": 4096, "messages": historical["input"], "seed": 17041,
              "temperature": 0.6, "tools": [], "chat_template_kwargs": {"enable_thinking": False}}
    def factory(request, seed):
        assert request == historical and seed == native["seed"]
        return native
    live = request_with_output_budget(factory, historical, 17041, DEFAULT_MAX_OUTPUT_TOKENS)
    assert live["max_tokens"] == 16384
    assert {k: v for k, v in live.items() if k != "max_tokens"} == {
        k: v for k, v in native.items() if k != "max_tokens"}
    assert native["max_tokens"] == 4096 and historical == original


@pytest.mark.parametrize("cap", [4096, 16384])
def test_context_boundary_reserves_the_selected_live_output_budget(cap):
    assert fits_context(131072 - cap, cap)
    assert not fits_context(131072 - cap + 1, cap)
    # The larger reservation must reject inputs the old 4k setting accepted.
    if cap == 16384:
        assert fits_context(120000, 4096) and not fits_context(120000, cap)


@pytest.mark.parametrize("bad", [0, -1, True, 16384.0, "16384", 131072])
def test_invalid_budget_rejected_before_request_construction(bad):
    def forbidden(*args):
        raise AssertionError("Invalid budget reached request construction")
    with pytest.raises(ValueError):
        request_with_output_budget(forbidden, {}, 1, bad)
    with pytest.raises(ValueError):
        validate_max_output_tokens(bad)


@pytest.mark.parametrize("transport", ["qwen", "muse"])
def test_actual_native_factory_changes_only_output_cap_and_retains_parse_errors(transport):
    pytest.importorskip("transformers")
    if transport == "qwen":
        from workflows.work1000_task import request_body
    else:
        from workflows.muse_task import request_body
    request = {"input": [{"role": "system", "content": "fixed"},
                          {"role": "user", "content": "same goal"}], "tools": []}
    baseline = request_body(request, 123)
    live = request_with_output_budget(request_body, request, 123, 16384)
    assert baseline["max_tokens"] == 4096
    assert live == dict(baseline, max_tokens=16384)
    malformed = deepcopy(request)
    malformed["input"].append({"type": "function_call", "name": "echo", "call_id": "bad",
                               "arguments": '{"content":"unfinished'})
    with pytest.raises(json.JSONDecodeError):
        request_with_output_budget(request_body, malformed, 123, 16384)
