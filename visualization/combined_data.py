"""Viewer data for the combined 1,000-token conversion cohort (combined_work1000).

Reads the frozen runs listed by combined_work1000/coverage.csv and paired-samples.csv:
600 Identity runs (200 task conditions x 3 seeds) and, for the 417 triggered prefixes,
six graph arms. No model calls. Per task condition it writes one gzip JSON file that
the page loads on demand; the seven arms of a seed share the Identity prefix, stored once.

Checks (appended to `issues`):
  * every replayed tool output equals the recorded output (all involved BFCL classes);
  * every turn-end filesystem tree equals the BFCL state log;
  * graph arms replay exactly the Identity prefix up to the trigger request;
  * the graph shown is the delivered payload (memory-metadata.json), whose step
    references all resolve to recorded tool returns.
"""
import base64
import copy
import csv
import gzip
import importlib
import inspect
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/bfcl_identity"
COMBINED = BASE / "combined_work1000"
ARMS = ("identity", "state-baseline", "state-optimized", "event-baseline",
        "event-optimized", "dedup-baseline", "dedup-optimized")
METHOD_LABEL = {"identity": "Identity", "state": "State-Transition Graph",
                "event": "Event Graph", "dedup": "Event Graph-Dedup"}
VARIANT_LABEL = {"baseline": "原格式", "optimized": "优化编码"}
STUDY_LABEL = {"lossless_encoding_v1": "文件系统", "mixed_tool_expansion": "混合工具"}
REPLAY_SOURCES = {"replay", "qwen_prefix_replay"}
SECRET_KEYS = {"password", "token", "api_key"}
UNCOMPARABLE = []  # turn-end trees that cannot be repr-compared (cyclic directories)


def arm_meta(arm):
    method, _, variant = arm.partition("-")
    label = METHOD_LABEL[method] + (f" · {VARIANT_LABEL[variant]}" if variant else "")
    return {"k": arm, "method": method, "variant": variant or None, "label": label}


class Env:
    """One replay session through BFCL's own executor (string conversion, method
    rewriting and eval), so environment state matches the recorded execution."""
    count = 0

    def __init__(self, entry, long_context, H):
        Env.count += 1
        self.H, self.entry, self.long_context = H, entry, long_context
        self.model = f"memory_viewer_{Env.count}"
        _, self.insts = H.MTU.execute_multi_turn_func_call(
            [], entry["initial_config"], entry["involved_classes"], self.model, entry["id"], long_context=long_context)
        self.owner = {}
        for cname, inst in self.insts.items():
            for name, _ in inspect.getmembers(inst, predicate=inspect.ismethod):
                if not name.startswith("_"):
                    self.owner[name] = cname

    def call(self, name, arguments):
        try:
            text = self.H.convert_to_function_call({name: arguments})[0]
        except Exception as exc:  # undecodable arguments never reach the executor
            return f"Error during execution: {exc}", None
        out, _ = self.H.MTU.execute_multi_turn_func_call(
            [text], self.entry["initial_config"], self.entry["involved_classes"], self.model, self.entry["id"],
            long_context=self.long_context)
        return out[0], self.owner.get(name)

    def close(self):
        g = vars(self.H.MTU)
        for key in [k for k in g if k.startswith(self.model)]:
            del g[key]


def _plain_state(inst):
    out = {}
    for key, value in vars(inst).items():
        if key.startswith("_"):
            continue
        if isinstance(value, set):
            value = sorted(value, key=str)
        if key in SECRET_KEYS:
            value = "••••"
        text = json.dumps(value, ensure_ascii=False, default=str)
        out[key] = text if len(text) <= 2400 else text[:2400] + "…"
    return out


def _snapshot(insts, H):
    snap = {}
    if "GorillaFileSystem" in insts:
        snap["fs"] = H.tree(insts["GorillaFileSystem"].root)
    dom = {c: _plain_state(i) for c, i in insts.items() if c != "GorillaFileSystem" and c not in H.STATELESS_CLASSES}
    if dom:
        snap["dom"] = dom
    return snap


def _cwd(insts, H):
    fs = insts.get("GorillaFileSystem")
    return H.cwd_path(fs) if fs else None


def _display(item, memory_text, H):
    if memory_text is not None and H.item_text(item).strip() == memory_text.strip():
        text = H.item_text(item)
        return {"k": "memory", "t": text, "n": len(text)}
    return H.display_message(item)


class TaskFile:
    """Collects one task condition's seeds, sharing env snapshots across arms."""

    def __init__(self):
        self.pool, self.index, self.toolsets, self.tool_index = [], {}, [], {}
        self.tool_docs = {}

    def snap(self, snap):
        key = json.dumps(snap, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if key not in self.index:
            self.index[key] = len(self.pool)
            self.pool.append(snap)
        return self.index[key]

    def toolset(self, tools, H):
        names = tuple(t["name"] for t in tools)
        if names not in self.tool_index:
            self.tool_index[names] = len(self.toolsets)
            self.toolsets.append(list(names))
            for t in H.tool_summary(tools):
                self.tool_docs.setdefault(t["name"], t)
        return self.tool_index[names]


def _replay_run(run_dir, entry, category, H, tf, issues, label, memory_text=None, export_from=0):
    api = json.load(open(run_dir / "api.json"))
    accounting = {a["index"]: a for a in json.load(open(run_dir / "accounting.json"))}
    long_context = category == "multi_turn_long_context"
    segments, steps = [], []
    for r, rec in enumerate(api):
        inp = rec["request"]["input"]
        if segments and len(inp) >= len(segments[-1]) and inp[: len(segments[-1])] == segments[-1]:
            segments[-1] = inp
        else:
            segments.append(inp)
        usage = rec["response"]["usage"]
        acc = accounting.get(r, {})
        steps.append({"turn": rec["turn"], "seg": len(segments) - 1, "n": len(inp),
                      "in": usage["input_tokens"], "out": usage["output_tokens"],
                      "cached": usage.get("input_tokens_details", {}).get("cached_tokens", 0),
                      "fixed": acc.get("fixed_tokens"), "work": acc.get("working_tokens"),
                      "replay": rec.get("source") in REPLAY_SOURCES,
                      "ts": tf.toolset(rec["request"].get("tools") or [], H),
                      "resp": [H.display_message(o) for o in rec["response"]["output"]]})
    recorded, first_seen = {}, {}
    for r, rec in enumerate(api):
        for item in rec["request"]["input"]:
            if item.get("type") == "function_call_output":
                recorded.setdefault(item["call_id"], item["output"])
                first_seen.setdefault(item["call_id"], r)
    env = Env(entry, long_context, H)
    insts = env.insts
    fs0 = tf.snap(_snapshot(insts, H))
    cwd0 = _cwd(insts, H)
    domains_used = Counter()
    for r, rec in enumerate(api):
        results = []
        for call in (o for o in rec["response"]["output"] if o.get("type") == "function_call"):
            out, cname = env.call(call["name"], call.get("arguments") or "{}")
            if cname:
                domains_used[cname] += 1
            saved = recorded.get(call["call_id"])
            if saved is not None and H.norm(saved) != H.norm(out):
                issues.append(f"{label} req{r} {call['name']}: replay output differs")
            results.append({"id": call["call_id"], "out": H.clip(saved if saved is not None else out, 6000),
                            "cwd": _cwd(insts, H), "dom": cname})
        steps[r]["res"] = results
        steps[r]["fs"] = tf.snap(_snapshot(insts, H))
        steps[r]["cwd"] = _cwd(insts, H)
    # Turn-end filesystem trees against BFCL's state log.
    full = json.load(open(run_dir / "full.json"))
    states = []
    for t in full["metadata"]["inference_log"]:
        if isinstance(t, list):
            fs_state = next((x for x in t if x.get("role") == "state_info" and x.get("class_name") == "GorillaFileSystem"), None)
            if fs_state is not None:
                states.append(fs_state["content"]["root"])
    if states and "GorillaFileSystem" in insts:
        turn_last = {}
        for r, s in enumerate(steps):
            turn_last[s["turn"]] = r
        for t, r in sorted(turn_last.items()):
            if t + 1 >= len(states):
                continue
            chk = Env(entry, long_context, H)
            for rr in range(r + 1):
                for call in (o for o in api[rr]["response"]["output"] if o.get("type") == "function_call"):
                    chk.call(call["name"], call.get("arguments") or "{}")
            try:
                if repr(chk.insts["GorillaFileSystem"].root) != states[t + 1]:
                    issues.append(f"{label} turn {t}: replayed tree differs from BFCL state log")
            except RecursionError:  # cyclic directory: repr cannot be compared
                UNCOMPARABLE.append(f"{label} turn {t}")
            chk.close()
    env.close()
    run = {"segments": [[_display(m, memory_text, H) for m in seg] for seg in segments],
           "steps": steps[export_from:], "fs0": fs0, "cwd0": cwd0}
    return run, api, first_seen, domains_used


def _rows(table, columns):
    return {key: dict(zip(columns, row)) for key, row in (table or {}).items()}


def _source(payload, mid):
    """Source message mN as a dict, using the payload's column layout."""
    row = (payload.get("source_messages") or {}).get(mid)
    if not row:
        return {}
    kind, values = row[0], row[1:]
    return {"kind": kind, **dict(zip(payload["source_message_columns"].get(kind, []), values))}


def _event_export(payload, req_of_msg, H):
    events = _rows(payload.get("events"), payload.get("event_columns", []))
    step_req = {0: 0}
    for e in events.values():
        step_req[e["step"]] = req_of_msg(e.get("return_message"))
    at = lambda s: step_req.get(s, max(step_req.values()) if s else 0)
    nodes = []
    for oid, o in _rows(payload.get("objects"), payload.get("object_columns", [])).items():
        nodes.append({"id": oid, "c": "object", "s": o.get("first_observed_at", 0), "r": at(o.get("first_observed_at", 0)),
                      "d": True, "o": o.get("origin"), "dom": o.get("domain"), "et": o.get("entity_type"), "did": o.get("domain_id")})
    for fid, f in _rows(payload.get("facts"), payload.get("fact_columns", [])).items():
        value = f.get("value")
        node = {"id": fid, "c": "fact", "s": f.get("valid_from", 0), "r": at(f.get("valid_from", 0)), "d": True,
                "sub": f.get("subject"), "p": f.get("predicate"), "k": f.get("key"), "v": H.short(value),
                "ver": f.get("version"), "ret": f.get("retired_at"), "why": f.get("retired_reason"),
                "rr": at(f["retired_at"]) if f.get("retired_at") is not None else None}
        if f.get("predicate") == "binding" and isinstance(value, dict):
            node["name"] = value.get("name")
        nodes.append(node)
    for eid, e in events.items():
        call = _source(payload, e.get("input_message"))
        nodes.append({"id": eid, "c": "event", "s": e["step"], "r": at(e["step"]), "d": True,
                      "tool": e.get("tool"), "a": H.short(call.get("arguments", ""), 60), "st": e.get("status"),
                      "dom": e.get("domain")})
    by_id = {n["id"]: n for n in nodes}
    cols = payload.get("relation_columns", [])
    edges = []
    for row in payload.get("relations") or []:
        rel = dict(zip(cols, row)) if isinstance(row, list) else row
        if not isinstance(rel, dict) or rel.get("from") not in by_id or rel.get("to") not in by_id:
            continue
        edges.append({"f": rel["from"], "rel": rel.get("relation"), "t": rel["to"],
                      "r": max(by_id[rel["from"]]["r"], by_id[rel["to"]]["r"])})
    return {"kind": "event", "nodes": nodes, "edges": edges}


def _state_export(payload, req_of_msg, H):
    raw = payload.get("state_nodes") or {}
    edges_in = payload.get("tool_call_edges") or {}
    into = {e["to"]: (eid, e) for eid, e in edges_in.items()}
    cwd, objects, domain_updates = None, {}, 0
    nodes = []
    for sid in sorted(raw, key=lambda s: int(s[1:])):
        node = raw[sid]
        changes = node.get("changes") if "inherits" in node else None
        parts = []
        if changes is None:
            cwd = (node.get("cwd") or {}).get("value")
            objects = {i: o for i, o in enumerate(node.get("objects") or [])}
        else:
            if "cwd" in changes:
                cwd = changes["cwd"].get("value")
                parts.append(f"工作目录 → {cwd or '未知'}")
            updated = changes.get("objects_updated") or []
            for o in updated:
                objects[o.get("object_index")] = o
            if updated:
                names = [str(o.get("name")) for o in updated[:4]]
                parts.append("对象 " + "、".join(names) + (f" 等 {len(updated)} 个" if len(updated) > 4 else ""))
            dsu = changes.get("domain_state_updates")
            if dsu:
                n = len(dsu) if isinstance(dsu, (list, dict)) else 1
                domain_updates += n
                parts.append(f"其他工具状态更新 {n} 项")
        eid, edge = into.get(sid, (None, None))
        r = req_of_msg(edge.get("return_message")) if edge else 0
        nodes.append({"id": sid, "desc": "；".join(parts) or ("初始状态：工作目录未知" if changes is None else "无可观察的状态变化"),
                      "cwd": cwd, "objs": len(objects), "r": r, "d": True})
    edges = []
    for eid, e in edges_in.items():
        call = _source(payload, e.get("input_message"))
        edges.append({"id": eid, "f": e["from"], "t": e["to"], "tool": e.get("tool"), "a": H.short(call.get("arguments", ""), 60),
                      "st": e.get("status"), "r": req_of_msg(e.get("return_message"))})
    return {"kind": "state", "nodes": nodes, "edges": edges}


def build(H, out_dir, dataset, issues, log=print, only=None):
    """Write per-task gzip files under out_dir; return the index embedded in the page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    coverage = list(csv.DictReader(open(COMBINED / "coverage.csv")))
    paired = {p["sample_id"]: p for p in csv.DictReader(open(COMBINED / "paired-samples.csv"))}
    arm_rows = defaultdict(dict)
    for a in csv.DictReader(open(COMBINED / "arm-results.csv")):
        arm_rows[a["sample_id"]][a["arm"]] = a
    by_task = defaultdict(list)
    for c in coverage:
        by_task[(c["source_study"], c["task"])].append(c)
    tasks = []
    for (study, task_id), rows in sorted(by_task.items(), key=lambda kv: (kv[0][0], kv[0][1].rsplit("_", 1)[0], int(kv[0][1].rsplit("_", 1)[1]))):
        if only and f"{study}/{task_id}" not in only:
            continue
        entry = dataset[task_id]
        category = rows[0]["category"]
        tf = TaskFile()
        seeds_out, seeds_index = [], []
        for c in sorted(rows, key=lambda x: int(x["seed"])):
            sid = c["sample_id"]
            seed_dir = BASE / study / "evaluation" / task_id / f"seed{c['seed']}"
            triggered = c["triggered"] == "True"
            ident, id_api, first_seen, domains = _replay_run(seed_dir / "identity", entry, category, H, tf, issues, f"{sid}/identity")
            id_manifest = json.load(open(seed_dir / "identity" / "manifest.json"))
            id_score = json.load(open(seed_dir / "identity" / "official-score.json"))
            ident.update(passed=bool(id_score["passed"]), reason=_reason(id_score))
            seed = {"seed": int(c["seed"]), "triggered": triggered, "identity": ident, "arms": {}}
            idx = {"seed": int(c["seed"]), "triggered": triggered, "passed": {"identity": ident["passed"]}}
            if triggered:
                p = paired[sid]
                trigger = int(p["trigger_request_index"])
                seed.update(trigger=trigger, triggerTurn=int(p["trigger_user_turn_index"]), sourceWork=int(p["source_work_tokens"]))
                # Did the converted prefix actually call a non-filesystem tool?
                prefix_domains = Counter()
                for st in ident["steps"][:trigger]:
                    for res in st["res"]:
                        if res["dom"]:
                            prefix_domains[res["dom"]] += 1
                seed["prefixDomains"] = dict(prefix_domains)
                idx.update(trigger=trigger, sourceWork=seed["sourceWork"],
                           mixedPrefix=any(d != "GorillaFileSystem" for d in prefix_domains))
                for arm in ARMS[1:]:
                    run_dir = seed_dir / arm
                    manifest = json.load(open(run_dir / "manifest.json"))
                    meta = json.load(open(run_dir / "memory-metadata.json"))
                    memory_text = (run_dir / "memory.txt").read_text()
                    run, api, _, _ = _replay_run(run_dir, entry, category, H, tf, issues, f"{sid}/{arm}",
                                                 memory_text=memory_text, export_from=trigger)
                    if [r["request"]["input"] for r in api[:trigger]] != [r["request"]["input"] for r in id_api[:trigger]]:
                        issues.append(f"{sid}/{arm}: prefix differs from Identity")
                    if manifest.get("trigger_index") != trigger:
                        issues.append(f"{sid}/{arm}: trigger {manifest.get('trigger_index')} != paired {trigger}")
                    score = json.load(open(run_dir / "official-score.json"))
                    if str(bool(score["passed"])) != p[f"{arm}_passed"]:
                        issues.append(f"{sid}/{arm}: score differs from paired-samples.csv")

                    def req_of_msg(mid, payload=meta["graph"]):
                        src = _source(payload, mid)
                        cid = src.get("call_id")
                        if cid is None or cid not in first_seen:
                            issues.append(f"{sid}/{arm}: graph reference {mid} has no recorded return")
                            return trigger
                        return first_seen[cid]
                    payload = meta["graph"]
                    graph = (_state_export if "state_nodes" in payload else _event_export)(payload, req_of_msg, H)
                    checkpoint = json.load(open(run_dir / "checkpoint-history.json"))
                    run.update(passed=bool(score["passed"]), reason=_reason(score), boundary=trigger,
                               memTokens=meta["total_tokens"], bodyTokens=meta["body_tokens"],
                               instrTokens=meta["instruction_tokens"], explanation=meta["explanation"],
                               variant=meta["candidate"], replaced=len(checkpoint), graph=graph,
                               firstInput=manifest.get("first_input"))
                    # Segments after the prefix: the first one carries the memory message.
                    seed["arms"][arm] = run
                    idx["passed"][arm] = run["passed"]
            seeds_out.append(seed)
            seeds_index.append(idx)
        # gzip + base64 text: artifact hosting serves .txt but not .gz; the page decodes both steps.
        fname = f"{study}__{task_id}.b64.txt"
        detail = {"pool": tf.pool, "toolsets": tf.toolsets, "tools": tf.tool_docs, "seeds": seeds_out}
        raw = json.dumps(detail, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (out_dir / fname).write_text(base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii"))
        questions = [q[0]["content"] if q else "" for q in entry["question"]]
        tasks.append({"key": f"{study}/{task_id}", "study": study, "task": task_id, "family": rows[0]["family"],
                      "category": category, "classes": entry["involved_classes"], "questions": questions,
                      "missed": entry.get("missed_function"), "file": fname, "seeds": seeds_index})
        log(study, task_id, [(s["seed"], s.get("trigger")) for s in seeds_index], (out_dir / fname).stat().st_size)
    summary = [r for r in csv.DictReader(open(COMBINED / "summary.csv"))]
    mixed_prefix = {f"{t['study']}/{t['task']}/seed{s['seed']}": s.get("mixedPrefix", False)
                    for t in tasks for s in t["seeds"] if s["triggered"]}
    cohorts = _cohorts(arm_rows, mixed_prefix, summary, issues)
    return {"arms": [arm_meta(a) for a in ARMS], "studies": STUDY_LABEL, "tasks": tasks, "summary": summary,
            "cohorts": cohorts, "threshold": 1000}


def _cohorts(arm_rows, mixed_prefix, summary, issues):
    """Per-cohort arm metrics from arm-results.csv. Post-conversion total per trajectory is
    mean_post_input_tokens x post_conversion_requests (the mean is over that trajectory's requests)."""
    defs = [
        ("all", "全部", lambda sid: True),
        ("lossless_encoding_v1", "文件系统研究", lambda sid: sid.startswith("lossless_encoding_v1/")),
        ("mixed_tool_expansion", "混合工具研究", lambda sid: sid.startswith("mixed_tool_expansion/")),
        ("mixed_prefix", "前缀含非文件调用", lambda sid: mixed_prefix.get(sid, False)),
        ("mixed_fs_only", "混合研究·前缀仅文件系统", lambda sid: sid.startswith("mixed_tool_expansion/") and not mixed_prefix.get(sid, False)),
    ]
    out = []
    for key, label, keep in defs:
        sids = [sid for sid in arm_rows if sid in mixed_prefix and keep(sid)]
        arms = []
        for arm in ARMS:
            rows = [arm_rows[sid][arm] for sid in sids]
            n = len(rows)
            mean = lambda xs: sum(xs) / len(xs) if xs else 0
            post_total = [float(r["mean_post_input_tokens"]) * int(r["post_conversion_requests"]) for r in rows]
            gains = sum(arm_rows[sid][arm]["passed"] == "True" and arm_rows[sid]["identity"]["passed"] == "False" for sid in sids)
            losses = sum(arm_rows[sid][arm]["passed"] == "False" and arm_rows[sid]["identity"]["passed"] == "True" for sid in sids)
            arms.append({"arm": arm, "n": n, "passed": sum(r["passed"] == "True" for r in rows),
                         "first": mean([float(r["first_input_tokens"]) for r in rows]),
                         "meanPost": mean([float(r["mean_post_input_tokens"]) for r in rows]),
                         "postTotal": mean(post_total),
                         "postReq": mean([int(r["post_conversion_requests"]) for r in rows]),
                         "gains": gains, "losses": losses})
        out.append({"key": key, "label": label, "n": len(sids), "arms": arms})
    # The pooled and per-study cohorts must reproduce the exported summary.
    for row in summary:
        cohort = next((c for c in out if c["key"] == row["cohort"]), None)
        mine = next((a for a in cohort["arms"] if a["arm"] == row["arm"]), None) if cohort else None
        if mine is None:
            continue
        if (mine["n"] != int(row["n"]) or mine["passed"] != int(row["passed"])
                or abs(mine["first"] - float(row["first_input_tokens"])) > 0.01
                or abs(mine["meanPost"] - float(row["mean_post_input_tokens"])) > 0.01
                or mine["gains"] != int(row["gains_vs_identity"]) or mine["losses"] != int(row["losses_vs_identity"])):
            issues.append(f"cohort {row['cohort']}/{row['arm']} differs from summary.csv")
    return out


def _reason(score):
    if score.get("passed"):
        return "passed"
    return ((score.get("diagnostics") or [{}])[0].get("error") or {}).get("error_type")
