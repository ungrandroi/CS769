"""History compression for the BFCL multi-turn FC loop.

Runs only when the caller asks (registry name or BFCL_HISTORY_MODE).
User messages stay verbatim. The latest assistant tool-call step and its
matching tool messages stay verbatim and paired. Older assistant/tool
messages are replaced by one summary. A previous summary is passed back
in as prev_summary and is not repeated inside history.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import tiktoken
from jinja2 import Environment, FileSystemLoader, StrictUndefined

SUMMARY_PREFIX = "<HISTORY_SUMMARY>"
TOKEN_THRESHOLD = 4096
COMPRESSOR_MODEL = "gpt-4.1-mini"

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_PROMPT_FILES = {
    "v2": "prompt_history_v2.jinja",
    "ut": "prompt_history_ut.jinja",
}

_enc = tiktoken.get_encoding("o200k_base")
_log_lock = threading.Lock()
_token_lock = threading.Lock()
_input_tokens = 0
_input_tokens_seeded = False
_stop_reason_logged = False


def history_mode(registry_name: str) -> str:
    override = os.getenv("BFCL_HISTORY_MODE", "").strip().lower()
    if override in {"v2", "naive", "hist"}:
        return "v2"
    if override == "ut":
        return "ut"
    if override in {"none", "off"}:
        return "none"
    name = registry_name or ""
    if "-ut-FC" in name:
        return "ut"
    if "-hist-FC" in name:
        return "v2"
    return "none"


def count_message_tokens(messages: list) -> int:
    return sum(count_text_tokens(_message_text(msg)) for msg in messages)


def count_text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc.encode(text, disallowed_special=()))


def maybe_compress(handler, inference_data: dict) -> None:
    mode = history_mode(getattr(handler, "registry_name", ""))
    if mode == "none":
        return
    messages = inference_data.get("message") or []
    if count_message_tokens(messages) <= TOKEN_THRESHOLD:
        return
    new_messages, stats = compress_messages(messages, mode, handler)
    if new_messages is None:
        return
    inference_data["message"] = new_messages
    _append_stat(
        handler,
        {
            "event": "compress",
            "id": getattr(handler, "_current_test_id", None),
            "mode": mode,
            "input_tokens": stats["input_tokens"],
            "output_tokens": stats["output_tokens"],
            "messages_before": stats["messages_before"],
            "messages_after": len(new_messages),
            "tokens_before": stats["tokens_before"],
            "tokens_after": count_message_tokens(new_messages),
            "summary": stats["summary"],
            "replaced_history": stats["replaced_history"],
        },
    )


def compress_messages(messages: list, mode: str, handler):
    last_step = _last_step_indices(messages)
    compressible = []
    prev_summaries = []
    for idx, msg in enumerate(messages):
        role = _role(msg)
        if role == "user" or idx in last_step:
            continue
        if role not in {"assistant", "tool"}:
            continue
        if _is_summary(msg):
            prev_summaries.append(msg)
        else:
            compressible.append(msg)
    if not compressible:
        return None, None

    task = "\n".join(
        _content_str(msg) for msg in messages if _role(msg) == "user"
    )
    prev_summary = ""
    if prev_summaries:
        prev_summary = _strip_summary_prefix(_content_str(prev_summaries[-1]))
    history = "\n\n".join(_format_for_history(msg) for msg in compressible)
    rendered = _render(mode, task=task, prev_summary=prev_summary, history=history)

    kwargs = {
        "model": COMPRESSOR_MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": rendered}],
    }
    if not getattr(handler, "_omit_store", False):
        kwargs["store"] = False
    api_response, _ = handler.generate_with_backoff(**kwargs)
    text = (api_response.choices[0].message.content or "").strip()
    if not text:
        return None, None
    if not text.lstrip().startswith(SUMMARY_PREFIX):
        text = SUMMARY_PREFIX + "\n" + text
    summary_msg = {"role": "assistant", "content": text}

    new_messages = []
    inserted = False
    for idx, msg in enumerate(messages):
        role = _role(msg)
        keep = role == "user" or idx in last_step
        if keep:
            new_messages.append(_to_api_dict(msg) if not isinstance(msg, dict) else msg)
            continue
        if not inserted:
            new_messages.append(summary_msg)
            inserted = True
    if not inserted:
        new_messages.append(summary_msg)

    usage = getattr(api_response, "usage", None)
    stats = {
        "input_tokens": getattr(usage, "prompt_tokens", None) or count_text_tokens(rendered),
        "output_tokens": getattr(usage, "completion_tokens", None) or count_text_tokens(text),
        "messages_before": len(messages),
        "tokens_before": count_message_tokens(messages),
        "summary": text,
        "replaced_history": history,
    }
    return new_messages, stats


def note_agent_usage(handler, input_tokens, output_tokens) -> None:
    global _input_tokens
    with _token_lock:
        _input_tokens += input_tokens or 0
    _append_stat(
        handler,
        {
            "event": "agent",
            "id": getattr(handler, "_current_test_id", None),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    )


def note_message_tokens(handler, messages: list) -> int:
    if not getattr(handler, "_azure_custom", False):
        return 0
    n = count_message_tokens(messages)
    users = sum(1 for msg in messages if _role(msg) == "user")
    _append_stat(
        handler,
        {
            "event": "messages_tokens",
            "id": getattr(handler, "_current_test_id", None),
            "tokens": n,
            "user_messages": users,
        },
    )
    return n


def dump_request(handler, messages: list, tools) -> None:
    path = os.getenv("BFCL_DUMP_REQUESTS", "").strip()
    if not path or not getattr(handler, "_azure_custom", False):
        return
    users = 0
    after_user = 0
    seen_user = False
    for msg in messages:
        if _role(msg) == "user":
            users += 1
            seen_user = True
            after_user = 0
        elif seen_user:
            after_user += 1
    record = {
        "id": getattr(handler, "_current_test_id", None),
        "registry": getattr(handler, "registry_name", None),
        "user_messages": users,
        "messages_after_last_user": after_user,
        "messages": [_to_api_dict(msg) for msg in messages],
        "tools": tools,
    }
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _log_lock:
        with dest.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def seed_input_token_counter(handler) -> None:
    """Load agent input tokens already written for this stats file.

    A restarted process (for example after raising the thread count) must
    keep counting toward the same budget.
    """
    global _input_tokens, _input_tokens_seeded
    with _token_lock:
        if _input_tokens_seeded:
            return
        path = _stats_path(handler)
        total = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("event") == "agent":
                    total += record.get("input_tokens") or 0
        _input_tokens = total
        _input_tokens_seeded = True


def scheduling_should_stop() -> str | None:
    """Reason to avoid submitting another test case, if any."""
    global _stop_reason_logged
    stop = os.getenv("BFCL_STOP_FILE", "").strip()
    if stop and Path(stop).exists():
        reason = f"stop file present: {stop}"
    else:
        raw = os.getenv("BFCL_INPUT_TOKEN_BUDGET", "").strip()
        if not raw:
            return None
        with _token_lock:
            used = _input_tokens
        budget = int(raw)
        if used < budget:
            return None
        reason = f"input tokens {used} >= budget {budget}"
    if not _stop_reason_logged:
        print(f"Stop scheduling new test cases: {reason}", flush=True)
        _stop_reason_logged = True
    return reason


def note_tool_return(handler, text: str) -> None:
    _append_stat(
        handler,
        {
            "event": "tool",
            "id": getattr(handler, "_current_test_id", None),
            "tokens": count_text_tokens(text or ""),
        },
    )


def note_rate_limit(handler) -> None:
    _append_stat(
        handler,
        {
            "event": "429",
            "id": getattr(handler, "_current_test_id", None),
        },
    )


def _stats_path(handler) -> Path:
    from bfcl_eval.constants.eval_config import PROJECT_ROOT

    registry = getattr(handler, "registry_dir_name", None) or getattr(
        handler, "registry_name", "unknown"
    )
    tag = os.getenv("BFCL_STATS_TAG", "").strip()
    name = f"{registry}.{tag}.jsonl" if tag else f"{registry}.jsonl"
    return PROJECT_ROOT / "logs" / "bfcl_stats" / name


def _append_stat(handler, record: dict) -> None:
    path = _stats_path(handler)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _log_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _render(mode: str, **kwargs) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_PROMPT_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
    )
    return env.get_template(_PROMPT_FILES[mode]).render(**kwargs)


def _last_step_indices(messages: list) -> set[int]:
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if _role(msg) != "assistant":
            continue
        calls = _tool_calls(msg)
        if not calls:
            continue
        ids = set()
        for call in calls:
            if isinstance(call, dict):
                ids.add(call.get("id"))
            else:
                ids.add(getattr(call, "id", None))
        ids.discard(None)
        j = i + 1
        matched = []
        ok = True
        while j < len(messages) and _role(messages[j]) == "tool":
            tid = _tool_call_id(messages[j])
            if ids and tid not in ids:
                ok = False
                break
            matched.append(j)
            j += 1
        if not ok:
            continue
        if all(_role(messages[k]) == "user" for k in range(j, len(messages))):
            return {i, *matched}
    return set()


def _is_summary(msg) -> bool:
    return _content_str(msg).lstrip().startswith(SUMMARY_PREFIX)


def _strip_summary_prefix(text: str) -> str:
    body = text.lstrip()
    if body.startswith(SUMMARY_PREFIX):
        body = body[len(SUMMARY_PREFIX) :].lstrip("\n")
    return body


def _format_for_history(msg) -> str:
    role = _role(msg)
    content = _content_str(msg)
    calls = _tool_calls(msg)
    if calls:
        rendered = []
        for call in calls:
            if isinstance(call, dict):
                fn = call.get("function") or {}
                rendered.append(f"{fn.get('name')}({fn.get('arguments')})")
            else:
                fn = getattr(call, "function", None)
                rendered.append(f"{getattr(fn, 'name', '')}({getattr(fn, 'arguments', '')})")
        extra = "tool_calls: " + "; ".join(rendered)
        content = f"{content}\n{extra}" if content else extra
    if role == "tool":
        return f"[tool id={_tool_call_id(msg)}] {content}"
    return f"[{role}] {content}"


def _message_text(msg) -> str:
    return _format_for_history(msg)


def _to_api_dict(msg) -> dict:
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "model_dump"):
        raw = msg.model_dump(exclude_none=True)
    else:
        raw = {
            "role": getattr(msg, "role", None),
            "content": getattr(msg, "content", None),
        }
    out = {"role": raw.get("role")}
    if raw.get("content") is not None:
        out["content"] = raw.get("content")
    if raw.get("tool_call_id"):
        out["tool_call_id"] = raw["tool_call_id"]
    calls = raw.get("tool_calls") or _tool_calls(msg)
    if calls:
        dumped = []
        for call in calls:
            if isinstance(call, dict):
                dumped.append(
                    {
                        "id": call.get("id"),
                        "type": call.get("type") or "function",
                        "function": {
                            "name": (call.get("function") or {}).get("name"),
                            "arguments": (call.get("function") or {}).get("arguments"),
                        },
                    }
                )
            else:
                fn = getattr(call, "function", None)
                dumped.append(
                    {
                        "id": getattr(call, "id", None),
                        "type": getattr(call, "type", None) or "function",
                        "function": {
                            "name": getattr(fn, "name", None),
                            "arguments": getattr(fn, "arguments", None),
                        },
                    }
                )
        out["tool_calls"] = dumped
    return out


def _role(msg) -> str | None:
    if isinstance(msg, dict):
        return msg.get("role")
    return getattr(msg, "role", None)


def _content_str(msg) -> str:
    if isinstance(msg, dict):
        content = msg.get("content")
    else:
        content = getattr(msg, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _tool_calls(msg):
    if isinstance(msg, dict):
        return msg.get("tool_calls") or []
    return getattr(msg, "tool_calls", None) or []


def _tool_call_id(msg):
    if isinstance(msg, dict):
        return msg.get("tool_call_id")
    return getattr(msg, "tool_call_id", None)
