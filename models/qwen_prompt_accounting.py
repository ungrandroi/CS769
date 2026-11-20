"""Offline native-Qwen prompt accounting for the saved BFCL trajectories.

This is a protocol/rendering adapter, not an agent, graph transform, or inference
runner. The trajectories were generated previously by another model. Rendering
them with the local GGUF's exact chat template is an explicit counterfactual.

The Chat-style mapping retains exact raw Responses items in ``responses_item``
metadata, including raw arguments and call IDs. Native Qwen rendering consumes
parsed parameter mappings, omits protocol IDs, and trims message text because
the model's own template does so. Those model-format choices are not changes to
the saved histories; compact wire-JSON remains a distinct audit comparator.

The reproducible profile disables both generation thinking and preservation of
historical thinking. No reasoning is fabricated. Developer messages remain
developer messages in the mapping; if unsupported by the supplied native
template, rendering fails instead of changing their instruction role.
"""

from copy import deepcopy
import json
import math

from transformers.utils.chat_template_utils import _compile_jinja_template


PROMPT_PROFILE = {
    "kind": "offline_counterfactual_native_gguf_chat_template",
    "source_history_model": "gpt-4o-mini-2024-07-18",
    "enable_thinking": False,
    "preserve_thinking": False,
    "add_generation_prompt": True,
    "tool_schema": "Responses flat function definitions nested under function; every field retained",
    "arguments": "exact raw JSON retained in responses_item; strict parsed object used by native parameter rendering",
    "protocol_metadata": "retained in Chat mapping; emitted only where native template consumes it",
    "renderer": "transformers.utils.chat_template_utils._compile_jinja_template (sandboxed Jinja)",
    "scope": "text-only; unknown meaningful item/content types rejected",
}


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate argument key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON argument constant: {value}")


def _arguments(raw):
    if isinstance(raw, dict):
        result = deepcopy(raw)
    elif isinstance(raw, str):
        if raw == "":
            # The native template explicitly recognizes this empty form.
            return raw
        result = json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                            parse_constant=_invalid_constant)
    else:
        raise ValueError("Tool arguments must be an object or exact JSON object string")
    if not isinstance(result, dict):
        raise ValueError("Native Qwen parameter rendering requires an argument object")

    def validate(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite tool argument")
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise ValueError("Tool argument keys must be strings")
            for child in value.values():
                validate(child)
        elif isinstance(value, list):
            for child in value:
                validate(child)
        elif value is not None and not isinstance(value, (str, bool, int, float)):
            raise ValueError("Unsupported tool argument type")

    validate(result)
    return result


def _content(value):
    if value is None or isinstance(value, str):
        return deepcopy(value)
    if not isinstance(value, list):
        raise ValueError("Unsupported message content type")
    for part in value:
        if not isinstance(part, dict) or part.get("type") not in ("text", "input_text", "output_text"):
            raise ValueError("Only explicit text content parts are supported")
        if not isinstance(part.get("text"), str):
            raise ValueError("Text content part is missing exact text")
        unknown = set(part) - {"type", "text", "annotations", "logprobs"}
        if unknown or part.get("annotations") not in (None, []) or part.get("logprobs") not in (None, []):
            raise ValueError("Unmodeled nonempty text-part metadata")
    return deepcopy(value)


def _metadata(item, allowed, empty=()):
    unknown = set(item) - set(allowed)
    if unknown:
        raise ValueError(f"Unsupported meaningful message fields: {sorted(unknown)}")
    for name in empty:
        if item.get(name) is not None:
            raise ValueError(f"Unsupported nonempty metadata: {name}")
    if "status" in item and item["status"] != "completed":
        raise ValueError("Only completed saved API items are supported")


def _call(item):
    _metadata(item, {"arguments", "call_id", "name", "type", "id", "async", "caller", "namespace", "status"},
              empty=("async", "caller", "namespace"))
    if not isinstance(item.get("call_id"), str) or not isinstance(item.get("name"), str):
        raise ValueError("Function call is missing its name or call ID")
    if "arguments" not in item:
        raise ValueError("Function call is missing arguments")
    return {"id": item["call_id"], "type": "function",
            "function": {"name": item["name"], "arguments": _arguments(item["arguments"])},
            "responses_item": deepcopy(item)}


def to_chat_messages(messages):
    """Map exact saved Responses items to native-template Chat-style messages.

    Consecutive function-call items become one assistant tool-call message;
    every call remains in its original order. Results remain individually
    paired by tool_call_id. No item is silently dropped. All original Responses
    records are retained verbatim in ``responses_item`` metadata.
    """
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    result, seen, pending = [], set(), set()
    previous_was_call = False
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("Every input item must be an object")
        kind = item.get("type")
        if kind == "function_call":
            call = _call(item)
            if call["id"] in seen:
                raise ValueError("Duplicate tool-call ID")
            seen.add(call["id"])
            pending.add(call["id"])
            if previous_was_call:
                result[-1]["tool_calls"].append(call)
            else:
                result.append({"role": "assistant", "content": "", "tool_calls": [call]})
            previous_was_call = True
            continue
        previous_was_call = False
        if kind == "function_call_output":
            _metadata(item, {"type", "call_id", "output"})
            if item.get("call_id") not in pending:
                raise ValueError("Tool result has no unmatched preceding call ID")
            if not isinstance(item.get("output"), str):
                raise ValueError("Only exact text tool outputs are supported")
            pending.remove(item["call_id"])
            result.append({"role": "tool", "tool_call_id": item["call_id"],
                           "content": item["output"], "responses_item": deepcopy(item)})
            continue
        if kind not in (None, "message"):
            raise ValueError(f"Unsupported Responses item type: {kind!r}")
        role = item.get("role")
        if role not in {"system", "developer", "user", "assistant"}:
            raise ValueError(f"Unsupported source message role: {role!r}")
        _metadata(item, {"role", "content", "id", "status", "type", "phase"}, empty=("phase",))
        if "content" not in item:
            raise ValueError("Message is missing content")
        # Copy known SDK metadata as well. Native Jinja consumes role/content;
        # callers can still inspect the exact original record in the mapping.
        message = deepcopy(item)
        message["content"] = _content(item["content"])
        result.append(message)
    return result


def to_chat_tools(tools):
    """Nest flat Responses function definitions without filtering any fields."""
    if tools is None:
        return []
    if not isinstance(tools, list):
        raise ValueError("tools must be a list")
    result = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ValueError("Only function tool definitions are supported")
        if "function" in tool:
            if not isinstance(tool["function"], dict):
                raise ValueError("Nested function definition must be an object")
            nested = deepcopy(tool)
        else:
            nested = {"type": "function", "function": {key: deepcopy(value) for key, value in tool.items() if key != "type"}}
        if not isinstance(nested["function"].get("name"), str):
            raise ValueError("Tool definition is missing name")
        result.append(nested)
    return result


def render_prompt(messages, tools, chat_template, enable_thinking=False, *, preserve_thinking=False):
    """Render a full hypothetical prompt with exact supplied native template.

    All schema text and the assistant generation prefix are included. Defaults
    are the documented non-thinking profile, not an inference claim. Tool-call
    IDs, raw wire metadata and outer text whitespace follow the supplied native
    template's own rendering rules; they remain intact in the source/mapping.
    """
    if type(enable_thinking) is not bool or type(preserve_thinking) is not bool:
        raise ValueError("Thinking profile values must be explicit booleans")
    if not isinstance(chat_template, str) or not chat_template:
        raise ValueError("An exact native chat template must be supplied")
    mapped = to_chat_messages(messages)
    definitions = to_chat_tools(tools)
    if any(message["role"] == "developer" for message in mapped):
        raise ValueError("The selected native Qwen template does not support developer roles; no role conversion is performed")
    template = _compile_jinja_template(chat_template)
    return template.render(messages=mapped, tools=definitions,
                           enable_thinking=enable_thinking,
                           preserve_thinking=preserve_thinking,
                           add_generation_prompt=True, add_vision_id=False,
                           bos_token="<|endoftext|>", eos_token="<|im_end|>")
