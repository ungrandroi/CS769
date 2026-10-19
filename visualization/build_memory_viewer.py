"""Build the step-by-step memory viewer data from saved Qwen 27B runs.

Experiments: qwen27b_experiment (Identity / State-Transition Graph / Event Graph),
qwen27b_dedup_eval (Event Graph-Dedup, same shared first turn), and the prepared
history1000 checkpoints (no inference yet; only the trigger point and the graphs
that conversion would deliver, which the history prefix fully determines).

No model calls. For every task x method it:
  * reads the saved API tape (exact request inputs, responses, usage);
  * replays every tool call in a fresh official GorillaFileSystem to recover the
    environment after each model call, checking each output against the tape and
    each turn-end tree against the saved BFCL state log;
  * rebuilds the V1/V2 graph over the run's whole visible history with the batch's
    own builder snapshot (source_code/). Only nodes up to the replacement step were
    actually delivered as graph memory; later nodes are marked as offline rebuilds.
Output: a JSON data file, then embedded into the viewer HTML template.
"""
import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "experiments/bfcl_identity/qwen27b_experiment"
DEDUP = ROOT / "experiments/bfcl_identity/qwen27b_dedup_eval"
HISTORY = ROOT / "experiments/bfcl_identity/history1000_eval"
BFCL = ROOT / "vendor/gorilla/berkeley-function-call-leaderboard"
MODES = ("identity", "v1-compact", "v2-compact", "v2-dedup")
LABELS = {"identity": "Identity", "v1-compact": "State-Transition Graph",
          "v2-compact": "Event Graph", "v2-dedup": "Event Graph-Dedup"}
THRESHOLD = 1000
MODEL = {"key": "qwen38-27b", "label": "Qwen3.8-27B-Q8_0", "note": "本地 GGUF · temperature 0 · seed 42"}

sys.path.insert(0, str(BATCH / "source_code"))
sys.path.insert(0, str(BFCL))
from graph_memory import GraphMemory  # noqa: E402  (batch snapshot)
from graph_memory_v2 import GraphMemoryV2  # noqa: E402
fs_mod = importlib.import_module("bfcl_eval.eval_checker.multi_turn_eval.func_source_code.gorilla_file_system")


def run_dir_for(task_id, mode):
    return DEDUP / "tasks" / task_id if mode == "v2-dedup" else BATCH / "tasks" / task_id / mode


TOOLSETS = set()
CLIP = 1400        # characters of a message kept for display
FILE_PREVIEW = 160  # characters of file content kept in tree snapshots


def clip(text, limit=CLIP):
    text = "" if text is None else str(text)
    return {"t": text, "n": len(text)} if len(text) <= limit else {"t": text[:limit], "n": len(text)}


def load_dataset():
    out = {}
    for name in ("multi_turn_base", "multi_turn_long_context"):
        for line in open(BFCL / f"bfcl_eval/data/BFCL_v4_{name}.json"):
            entry = json.loads(line)
            out[entry["id"]] = entry
    return out


def item_text(item):
    content = item.get("content")
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return content or ""


def display_message(item):
    if item.get("type") == "function_call":
        return {"k": "call", "name": item["name"], "args": item.get("arguments", "{}"), "id": item["call_id"]}
    if item.get("type") == "function_call_output":
        return {"k": "output", "id": item["call_id"], **clip(item.get("output"))}
    role = item.get("role")
    text = item_text(item)
    if role == "assistant" and text.startswith("[GraphMemory"):
        return {"k": "memory", "t": text, "n": len(text)}
    return {"k": role or item.get("type", "?"), **clip(text)}


def tree(node):
    if isinstance(node, fs_mod.Directory):
        return {"n": node.name, "c": [tree(child) for child in node.contents.values()]}
    content = node.content or ""
    return {"n": node.name, "f": content[:FILE_PREVIEW], "l": len(content)}


def cwd_path(fs):
    parts, d = [], fs._current_dir
    while d is not None:
        parts.append(d.name)
        d = d.parent
    return "/" + "/".join(reversed(parts))


def norm(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def execute(fs, name, args):
    try:
        result = getattr(fs, name)(**args)
    except Exception as exc:  # BFCL reports exceptions as text
        return f"Error during execution: {exc}"
    return json.dumps(result) if isinstance(result, dict) else str(result)


def short(value, limit=90):
    if isinstance(value, dict) and ("name" in value or "value" in value):
        value = value.get("name") or value.get("value") or value.get("location_id")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def v2_export(graph, visible_at, delivered_step):
    nodes = []
    for n in graph["nodes"]:
        step = n.get("step", n.get("first_observed_at", 0))
        out = {"id": n["id"], "c": n["category"], "s": step, "r": visible_at(step),
               "d": delivered_step is not None and step <= delivered_step}
        if n["category"] == "object":
            out["o"] = n.get("origin")
        elif n["category"] == "fact":
            out.update(sub=n["subject"], p=n["predicate"], k=n.get("key"), v=short(n.get("value")),
                       ver=n.get("version"), ret=n.get("retired_at"),
                       rr=visible_at(n["retired_at"]) if n.get("retired_at") is not None else None,
                       why=n.get("retired_reason"))
            if n["predicate"] == "binding" and isinstance(n.get("value"), dict):
                out["name"] = n["value"].get("name")
        elif n["category"] == "event":
            out.update(tool=n.get("tool"), a=short(n.get("arguments"), 60), st=n.get("status"))
        nodes.append(out)
    edges = [{"f": e["from"], "rel": e["relation"], "t": e["to"], "s": e.get("at_step", 0),
              "r": visible_at(e.get("at_step", 0))} for e in graph["edges"]]
    return {"nodes": nodes, "edges": edges}


def v1_export(graph, visible_at, delivered_step):
    nodes = []
    for i, n in enumerate(graph["nodes"]):
        objs = n["state"]["objects"]
        nodes.append({"id": n["id"], "desc": n["description"], "cwd": n["state"]["cwd"]["value"],
                      "objs": len(objs), "known": sum(1 for o in objs if o.get("exists")),
                      "r": visible_at(i), "d": delivered_step is not None and i <= delivered_step})
    edges = [{"id": e["id"], "f": e["from"], "t": e["to"], "tool": e["tool"], "a": short(e["arguments"], 60),
              "st": e["status"], "r": visible_at(e["sequence"] + 1)} for e in graph["edges"]]
    return {"nodes": nodes, "edges": edges}


def history_size(history, count):
    """history1000 metric, as in scripts/workflows/checkpoints.py."""
    calls = [m for m in history if m.get("type") == "function_call"]
    returns = [m for m in history if m.get("type") == "function_call_output"]
    ids, out_ids = [m["call_id"] for m in calls], [m["call_id"] for m in returns]
    if len(set(ids)) != len(ids) or len(set(out_ids)) != len(out_ids) or set(ids) != set(out_ids):
        return None
    return sum(count(m["name"] + "(" + m["arguments"] + ")") for m in calls) + sum(count(m["output"]) for m in returns)


def build_run(task_id, category, mode, entry, issues):
    run_dir = run_dir_for(task_id, mode)
    api = json.load(open(run_dir / f"{task_id}.api.json"))
    for rec in api:
        TOOLSETS.add(json.dumps(rec["request"]["tools"], sort_keys=True))
    manifest = json.load(open(run_dir / "manifest.json"))
    score = json.load(open(run_dir / "official-score.json"))
    long_context = category == "multi_turn_long_context"

    # Context segments: consecutive requests whose inputs extend the previous input.
    segments, steps = [], []
    for r, rec in enumerate(api):
        inp = rec["request"]["input"]
        if segments and len(inp) >= len(segments[-1]) and inp[: len(segments[-1])] == segments[-1]:
            segments[-1] = inp
        else:
            segments.append(inp)
        usage = rec["response"]["usage"]
        steps.append({"turn": rec["turn"], "seg": len(segments) - 1, "n": len(inp),
                      "in": usage["input_tokens"], "out": usage["output_tokens"],
                      "cached": usage.get("input_tokens_details", {}).get("cached_tokens", 0),
                      "replay": rec["source"] != "live_local_qwen",
                      "resp": [display_message(o) for o in rec["response"]["output"]]})

    # Recorded tool outputs, by call ID, and the first request that sees each one.
    recorded, first_seen = {}, {}
    for r, rec in enumerate(api):
        for item in rec["request"]["input"]:
            if item.get("type") == "function_call_output":
                recorded.setdefault(item["call_id"], item["output"])
                first_seen.setdefault(item["call_id"], r)

    # Replay the environment.
    fs = fs_mod.GorillaFileSystem()
    fs._load_scenario(entry["initial_config"]["GorillaFileSystem"], long_context=long_context)
    pool, index = [], {}
    cwd0 = cwd_path(fs)

    def snap():
        key = json.dumps(tree(fs.root), ensure_ascii=False, separators=(",", ":"))
        if key not in index:
            index[key] = len(pool)
            pool.append(json.loads(key))
        return index[key]

    initial = snap()
    for r, rec in enumerate(api):
        calls = [o for o in rec["response"]["output"] if o.get("type") == "function_call"]
        results = []
        for call in calls:
            out = execute(fs, call["name"], norm(call.get("arguments", "{}")) or {})
            saved = recorded.get(call["call_id"])
            if saved is not None and norm(saved) != norm(out):
                issues.append(f"{task_id}/{mode} req{r} {call['name']}: replay output differs")
            results.append({"id": call["call_id"], "out": clip(saved if saved is not None else out, 6000),
                            "recorded": saved is not None, "cwd": cwd_path(fs)})
        steps[r]["res"] = results
        steps[r]["fs"] = snap()
        steps[r]["cwd"] = cwd_path(fs)

    # Check turn-end trees against BFCL's own state log.
    full = json.load(open(run_dir / f"{task_id}.full.json"))
    states = [t[0]["content"]["root"] for t in full["metadata"]["inference_log"]
              if isinstance(t, list) and t and t[0].get("role") == "state_info"]
    turn_last = {}
    for r, s in enumerate(steps):
        turn_last[s["turn"]] = r
    fs_check = fs_mod.GorillaFileSystem()
    checked = 0
    for t, r in sorted(turn_last.items()):
        if t + 1 < len(states):
            fs_check._load_scenario(entry["initial_config"]["GorillaFileSystem"], long_context=long_context)
            for rr in range(r + 1):
                for call in (o for o in api[rr]["response"]["output"] if o.get("type") == "function_call"):
                    execute(fs_check, call["name"], norm(call.get("arguments", "{}")) or {})
            if repr(fs_check.root) != states[t + 1]:
                issues.append(f"{task_id}/{mode} turn {t}: replayed tree differs from BFCL state log")
            checked += 1

    # Logical visible history for graph rebuilds.
    last = api[-1]
    tail = [o for o in last["response"]["output"]]
    if mode == "identity":
        logical = last["request"]["input"] + tail
        boundary_req, delivered_step = None, None
    else:
        boundary_req = next(r for r, rec in enumerate(api) if rec["turn"] >= 1)
        prefix = json.load(open(run_dir / "prefix-history.json"))
        post = api[-1]["request"]["input"]
        assert display_message(post[0])["k"] == "memory", f"{task_id}/{mode}: no memory message at boundary"
        logical = prefix + post[1:] + tail
        delivered = json.load(open(run_dir / f"{task_id}.graph.json"))
        delivered_step = delivered.get("current_step", len(delivered["nodes"]) - 1)

    outputs = [m["call_id"] for m in logical if m.get("type") == "function_call_output"]

    def visible_at(step):
        if step == 0:
            return 0
        if step - 1 < len(outputs):
            return first_seen.get(outputs[step - 1], len(api))
        return len(api)

    graph = None
    if mode != "identity":
        builder = GraphMemory() if mode == "v1-compact" else GraphMemoryV2()
        g = builder.build(logical)
        graph = (v1_export if mode == "v1-compact" else v2_export)(g, visible_at, delivered_step)
        # The rebuilt prefix must agree with what was delivered.
        ids = {n["id"] for n in delivered["nodes"]}
        rebuilt = {n["id"] for n in graph["nodes"] if n["d"]}
        if ids != rebuilt:
            issues.append(f"{task_id}/{mode}: rebuilt delivered nodes differ ({len(ids)} vs {len(rebuilt)})")

    run_graph_inputs[(task_id, mode)] = (logical, visible_at, api)
    return {
        "passed": bool(score["passed"]),
        "reason": (score.get("diagnostics") or [{}])[0].get("error", {}).get("error_type") if not score["passed"] else "passed",
        "boundary": boundary_req, "memTokens": manifest.get("memory_tokens"),
        "replaced": (manifest.get("boundary") or {}).get("source_messages") if mode != "identity" else None,
        "segments": [[display_message(m) for m in seg] for seg in segments],
        "steps": steps, "pool": pool, "fs0": initial,
        "graph": graph, "turnChecks": checked, "cwd0": cwd0,
    }


run_graph_inputs = {}


def history1000(task_id, checkpoint, count, issues):
    """Per-request cumulative tool-content tokens on the Identity run, plus the
    graphs a conversion at the trigger would deliver (offline, no inference)."""
    logical, visible_at, api = run_graph_inputs[(task_id, "identity")]
    hist = [history_size(rec["request"]["input"], count) for rec in api]
    trigger = next((i for i, h in enumerate(hist) if h is not None and h >= THRESHOLD), None)
    expected = checkpoint["trigger_index"] if checkpoint else None
    if trigger != expected:
        issues.append(f"{task_id} history1000: trigger {trigger} != checkpoints.json {expected}")
    if checkpoint and trigger is not None and hist[trigger] != checkpoint["history_tokens"]:
        issues.append(f"{task_id} history1000: {hist[trigger]} tokens != checkpoints.json {checkpoint['history_tokens']}")
    out = {"hist": hist, "trigger": trigger, "graphs": None}
    if trigger is not None:
        delivered_step = sum(1 for m in api[trigger]["request"]["input"] if m.get("type") == "function_call_output")
        out["graphs"] = {"v1-compact": v1_export(GraphMemory().build(logical), visible_at, delivered_step),
                         "v2-compact": v2_export(GraphMemoryV2().build(logical), visible_at, delivered_step)}
        out["before"] = checkpoint["before"]
    return out


TOOL_PREFIX = "Tool description: "
TOOL_SUFFIX = " Note that the provided function is in Python 3 syntax."


def tool_summary(tools):
    out = []
    for t in tools:
        desc = t.get("description", "")
        desc = desc.split(TOOL_PREFIX, 1)[-1].replace(TOOL_SUFFIX, "").strip()
        params = t.get("parameters", {})
        req = set(params.get("required", []))
        out.append({"name": t["name"], "desc": desc,
                    "params": [{"n": k, "type": v.get("type"), "req": k in req, "d": (v.get("description") or "").strip()}
                               for k, v in params.get("properties", {}).items()]})
    return out


def tool_tokens(sample_request, sample_usage, issues):
    """Exact tool-definition cost: same messages rendered with and without tools.

    The serving template renders name/description/parameters only; the check
    against the saved usage of the sample request guards that assumption.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from qwen_prompt_accounting import render_prompt
    from local_qwen_tokenizer import LocalQwenTokenizer
    template = (BATCH / "runtime/chat-template.jinja").read_text()
    tools = [{k: v for k, v in t.items() if k != "response"} for t in sample_request["tools"]]
    with LocalQwenTokenizer() as tok:
        full = tok.count(render_prompt(sample_request["input"], tools, template), parse_special=True)
        bare = tok.count(render_prompt(sample_request["input"], [], template), parse_special=True)
    if full != sample_usage:
        issues.append(f"tool token check: rendered {full} != served {sample_usage}")
    return full - bare


def main():
    parser = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    parser.add_argument("--data-out", type=Path, default=here / "viewer-data.json")
    parser.add_argument("--template", type=Path, default=here / "memory_viewer_template.html")
    parser.add_argument("--html-out", type=Path, default=here / "index.html")
    args = parser.parse_args()
    dataset = load_dataset()
    plan = json.load(open(BATCH / "plan.json"))
    checkpoints = json.load(open(HISTORY / "checkpoints.json"))
    by_task = {c["id"]: c for c in checkpoints["tasks"]}
    sys.path.insert(0, str(ROOT / "scripts"))
    from local_qwen_tokenizer import LocalQwenTokenizer
    tasks, issues = [], []
    with LocalQwenTokenizer() as tok:
        for t in plan["tasks"]:
            entry = dataset[t["id"]]
            runs = {m: build_run(t["id"], t["category"], m, entry, issues) for m in MODES}
            h = history1000(t["id"], by_task.get(t["id"]), tok.count, issues)
            tasks.append({"id": t["id"], "category": t["category"], "family": t.get("family_id"),
                          "questions": [q[0]["content"] if q else "" for q in entry["question"]],
                          "runs": runs, "h1000": h})
            print(t["id"], {m: (r["passed"], len(r["steps"])) for m, r in runs.items()},
                  "h1000", h["trigger"], flush=True)
    if len(TOOLSETS) != 1:
        issues.append(f"{len(TOOLSETS)} different tool sets across requests")
    first = plan["tasks"][0]["id"]
    sample = json.load(open(BATCH / "tasks" / first / "identity" / f"{first}.api.json"))[0]
    tools = sample["request"]["tools"]
    model = {**MODEL, "tools": tool_summary(tools),
             "toolTokens": tool_tokens(sample["request"], sample["response"]["usage"]["input_tokens"], issues),
             "tasks": tasks}
    print("tool tokens:", model["toolTokens"])
    model["experiments"] = [
        {"key": "baseline", "label": "首轮后转换", "status": "complete",
         "modes": list(MODES), "note": "第 2 轮用户输入前把历史转换成记忆一次；Event Graph-Dedup 来自 qwen27b_dedup_eval，共用同一段首轮"},
        {"key": "history1000", "label": "1000-token 历史阈值转换", "status": checkpoints["status"],
         "modes": ["identity"], "pending": ["v1-compact", "v2-compact"], "threshold": checkpoints["threshold"],
         "metric": checkpoints["metric"], "triggered": len(checkpoints["tasks"]), "untriggered": len(checkpoints["untriggered"])},
    ]
    data = {"models": [model], "labels": LABELS, "issues": issues}
    args.data_out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print("issues:", len(issues))
    for i in issues[:40]:
        print("  ", i)
    print("bytes:", args.data_out.stat().st_size)
    if args.html_out:
        payload = args.data_out.read_text().replace("</", "<\\/")
        html = args.template.read_text().replace("__VIEWER_DATA__", payload, 1)
        args.html_out.write_text(html)
        print("html:", args.html_out, args.html_out.stat().st_size)


if __name__ == "__main__":
    main()
