"""Versioned objects, facts and execution events built from visible history only.

No LLM extraction, simulator access, GT or future questions. Tool effects follow
the pinned BFCL filesystem, with conservative invalidation outside that adapter.
V1 in graph_memory.py stays unchanged. This version still adds an index to the
original history; graph selection/compression is a separate experiment.
"""
from copy import deepcopy
import json

from graph_memory import FS_READS, FS_WRITES, parse, plain


RULE_VERSION = "bfcl-filesystem-v2.0"


class GraphMemoryV2:
    def __init__(self):
        self.graph = None

    def build(self, messages):
        source = plain(messages)
        self.graph = {
            "schema_version": 2, "representation": "object_fact_event_graph",
            "rule_version": RULE_VERSION, "source_policy": "visible_history_only",
            "delivery": "original_history_plus_graph_index",
            "nodes": [], "edges": [], "requests": [], "annotations": [],
            "source_messages": source, "pending_calls": [],
            "time_semantics": "observed tool-return sequence; not object creation time",
        }
        self.nodes, self.active, self.bindings, self.versions = {}, {}, {}, {}
        self.pending, self.seen_calls, self.goals = {}, set(), []
        self.step, self.event, self.refs = 0, None, []
        self.object_count, self.fact_count = 0, 0
        self._entity("session", "session")
        self._entity("l0", "initial_location")
        self._fact("session", "cwd", {"location_id": "l0", "value": None},
                   basis="unknown initial location; identity placeholder only")
        for index, message in enumerate(source):
            ref = f"m{index}"
            if message.get("role") == "user":
                self.goals.append(ref)
                self.graph["requests"].append({"id": ref, "content": message.get("content"),
                                               "after_step": self.step})
            if message.get("role") == "assistant" and message.get("content"):
                self.graph["annotations"].append({"evidence": ref, "after_step": self.step,
                    "kind": "assistant_statement", "verified_state": False})
            calls = message.get("tool_calls") or []
            if message.get("type") == "function_call":
                calls = [{"id": message["call_id"], "function": message}]
            for call in calls:
                call_id, function = call["id"], call["function"]
                if call_id in self.seen_calls:
                    raise ValueError(f"Duplicate call ID: {call_id}")
                self.seen_calls.add(call_id)
                self.pending[call_id] = {"call_id": call_id, "tool": function["name"],
                    "arguments": parse(function.get("arguments", "{}")), "call_evidence": ref}
            if message.get("type") == "function_call_output" or message.get("role") == "tool":
                call_id = message.get("call_id", message.get("tool_call_id"))
                if call_id not in self.pending:
                    raise ValueError(f"Tool output without a matching call: {call_id}")
                raw = message.get("output") if message.get("type") == "function_call_output" else message.get("content")
                self._execute(self.pending.pop(call_id), raw, ref)
        self.graph["pending_calls"] = list(self.pending.values())
        self.graph["current_step"] = self.step
        self.graph["active_fact_ids"] = list(self.active.values())
        self.graph["current_goal_refs"] = self.goals.copy()
        self.validate()
        return self.graph

    def _add(self, node):
        self.nodes[node["id"]] = node
        self.graph["nodes"].append(node)
        return node["id"]

    def _entity(self, identity=None, origin="observed_object"):
        if identity is None:
            identity = f"o{self.object_count}"
            self.object_count += 1
        return self._add({"id": identity, "category": "object", "origin": origin,
                          "first_observed_at": self.step})

    def _edge(self, source, relation, target, **attrs):
        # Relations describe recorded evidence and adapter resolution, never the
        # model's private reasoning. Repeated confirmations retain their events.
        edge = {"from": source, "relation": relation, "to": target,
                "at_step": self.step, **attrs}
        if any(all(e.get(k) == v for k, v in edge.items()) for e in self.graph["edges"]):
            return
        self.graph["edges"].append({"id": f"r{len(self.graph['edges'])}", **edge})

    def _get(self, subject, predicate, key=None):
        identity = self.active.get((subject, predicate, key))
        return self.nodes[identity] if identity else None

    def _retire(self, fact, reason):
        if not fact or fact["retired_at"] is not None:
            return
        fact.update(retired_at=self.step, retired_reason=reason,
                    retired_by=self.event["id"] if self.event else None)
        self.active.pop((fact["subject"], fact["predicate"], fact["key"]), None)
        if fact["predicate"] == "binding":
            v = fact["value"]
            self.bindings.pop((v["directory"], v["name"]), None)
        if self.event:
            self._edge(self.event["id"], "retires", fact["id"], reason=reason)

    def _support(self, fact, relation, basis, derived_from):
        if self.event:
            evidence = {"event": self.event["id"], "at_step": self.step,
                        "messages": self.refs.copy(), "basis": basis}
            if evidence not in fact["confirmations"]:
                fact["confirmations"].append(evidence)
            self._edge(self.event["id"], relation, fact["id"], rule=basis)
            for prior in derived_from:
                self._edge(fact["id"], "derived_from", prior,
                           event=self.event["id"], rule=basis)

    def _fact(self, subject, predicate, value, key=None, basis=None, derived_from=()):
        basis = basis or self.event["rule"]
        slot = (subject, predicate, key)
        old = self._get(*slot)
        if old and old["value"] == value:
            self._support(old, "confirms", basis, derived_from)
            return old
        self._retire(old, "superseded")
        self.versions[slot] = self.versions.get(slot, 0) + 1
        fact = {"id": f"f{self.fact_count}", "category": "fact", "subject": subject,
                "predicate": predicate, "key": key, "value": deepcopy(value),
                "version": self.versions[slot], "first_observed_at": self.step,
                "retired_at": None, "retired_reason": None, "retired_by": None,
                "basis": basis, "confirmations": []}
        self.fact_count += 1
        self._add(fact)
        self.active[slot] = fact["id"]
        self._edge(fact["id"], "describes", subject)
        if predicate == "binding":
            self.bindings[(value["directory"], value["name"])] = subject
            self._edge(fact["id"], "located_in", value["directory"])
        elif predicate == "cwd":
            self._edge(fact["id"], "current_directory", value["location_id"])
        elif predicate == "parent":
            self._edge(fact["id"], "parent_directory", value)
        self._support(fact, "supports", basis, derived_from)
        if old:
            self._edge(fact["id"], "supersedes", old["id"])
        return fact

    def _using(self, fact, role):
        if fact:
            self._edge(self.event["id"], "resolved_using", fact["id"],
                       role=role, rule=self.event["rule"], meaning="adapter resolution only")

    def _resolve(self, scope, name, role):
        if not isinstance(name, str):
            return None
        identity = self.bindings.get((scope, name))
        if identity:
            self._using(self._get(identity, "binding"), role)
            self._edge(self.event["id"], "acts_on", identity, role=role)
        return identity

    def _observe(self, scope, name, *, kind=None, content=None, new=False):
        if not isinstance(name, str):
            raise ValueError("Expected a local object name")
        identity = self.bindings.get((scope, name))
        if new and identity:
            self._invalidate_tree(identity, "replaced_by_observed_creation")
            identity = None
        identity = identity or self._entity()
        self._retire(self._get(scope, "entry_absent", name), "observed_present")
        self._fact(identity, "binding", {"directory": scope, "name": name})
        self._fact(identity, "exists", True)
        if kind is not None:
            self._fact(identity, "kind", kind)
        if content is not None:
            self._fact(identity, "content", content)
        return identity

    def _descendants(self, identity):
        found, queue = set(), [identity]
        while queue:
            parent = queue.pop()
            for (directory, _), child in list(self.bindings.items()):
                if directory == parent and child not in found and child != identity:
                    found.add(child)
                    queue.append(child)
        return found

    def _invalidate_tree(self, identity, reason, include_root=True):
        affected = self._descendants(identity) | ({identity} if include_root else set())
        for fid in list(self.active.values()):
            f = self.nodes[fid]
            if f["subject"] in affected:
                self._retire(f, reason)

    def _forget_all(self, reason):
        for fid in list(self.active.values()):
            self._retire(self.nodes[fid], reason)
        location = self._entity(origin="unknown_location_after_unmodeled_effect")
        self._fact("session", "cwd", {"location_id": location, "value": None},
                   basis="unknown location placeholder; effects unmodeled")

    def _execute(self, call, raw, output_ref):
        self.step += 1
        output = parse(raw)
        error = output.get("error") if isinstance(output, dict) else None
        failed = bool(error) or (isinstance(output, dict) and output.get("success") is False)
        self.refs = [call["call_evidence"], output_ref]
        self.event = {"id": f"a{self.step}", "category": "event", "step": self.step,
            **call, "output_raw": raw, "output": output, "output_evidence": output_ref,
            "status": "error" if failed else "success", "error": error,
            "status_basis": "tool return convention; not task completion",
            "rule": f"{RULE_VERSION}:{call['tool']}", "goal_refs": self.goals.copy()}
        self._add(self.event)
        tool = call["tool"]
        args = call["arguments"] if isinstance(call["arguments"], dict) else {}
        cwd = self._get("session", "cwd")
        scope = cwd["value"]["location_id"]
        if tool in FS_READS | FS_WRITES:
            self._using(cwd, "relative_path_context")
            for field in ("source", "destination", "file_name", "file_name1", "file_name2", "folder", "dir_name"):
                self._resolve(scope, args.get(field), field)
            if failed:
                description = f"{tool} 调用失败；保留错误，不应用成功后的状态变化。"
            else:
                description = self._filesystem(tool, args, output, scope)
        else:
            self._forget_all("unmodeled_effect")
            description = f"{tool} 的状态效果尚未建模；原有事实退出当前有效集合。"
        self.event["description"] = description

    def _filesystem(self, tool, args, result, scope):
        out = result if isinstance(result, dict) else {}
        if tool == "pwd" and isinstance(out.get("current_working_directory"), str):
            self._fact("session", "cwd", {"location_id": scope, "value": out["current_working_directory"]})
            return "已确认当前工作目录。"
        if tool == "cd":
            folder = str(args.get("folder", "")).rstrip("/") or "/"
            if folder == "..":
                binding, parent = self._get(scope, "binding"), self._get(scope, "parent")
                self._using(binding or parent, "parent_resolution")
                target = binding["value"]["directory"] if binding else parent["value"] if parent else self._entity(origin="observed_parent_location")
                self._fact(scope, "parent", target)
                label_fact = self._get(target, "binding")
                label = label_fact["value"]["name"] if label_fact else None
            elif folder == ".":
                target, label = scope, self._get("session", "cwd")["value"]["value"]
            elif folder == "/":
                root = self._get("session", "root")
                target = root["value"] if root else self._entity(origin="observed_root_location")
                self._fact("session", "root", target)
                label = out.get("current_working_directory")
            else:
                target = self._observe(scope, folder, kind="directory")
                label = folder
            self._fact("session", "cwd", {"location_id": target,
                       "value": out.get("current_working_directory", label)})
            return f"切换目录至 {label or '名称未知的位置'}；记录所用目录上下文。"
        if tool == "ls" and isinstance(out.get("current_directory_content"), list):
            names = out["current_directory_content"]
            for (directory, name), identity in list(self.bindings.items()):
                if directory == scope and name not in names and (args.get("a") or not name.startswith(".")):
                    self._invalidate_tree(identity, "absent_from_listing")
                    self._fact(scope, "entry_absent", True, key=name)
            for name in names:
                self._observe(scope, name)
            return f"观察到 {len(names)} 个名称；重复事实追加确认，类型保持未知。"
        if tool in ("mkdir", "touch") and result is None:
            name = args.get("dir_name" if tool == "mkdir" else "file_name")
            self._observe(scope, name, kind="directory" if tool == "mkdir" else "file",
                          content="" if tool == "touch" else None, new=True)
            return f"创建 {name}；分配新的对象身份。"
        if tool == "echo" and args.get("file_name") and result is None:
            self._observe(scope, args["file_name"], kind="file", content=args.get("content"))
            return f"更新 {args['file_name']} 的内容事实。"
        if tool == "cat" and "file_content" in out:
            self._observe(scope, args["file_name"], kind="file", content=out["file_content"])
            return f"观察 {args['file_name']} 的内容；保留来源。"
        if tool in ("mv", "cp") and "result" in out:
            return self._move_or_copy(tool, args, out, scope)
        if tool in ("rm", "rmdir") and "result" in out:
            name = args.get("file_name" if tool == "rm" else "dir_name")
            identity = self.bindings.get((scope, name)) or self._entity(origin="object_known_only_from_deletion")
            self._edge(self.event["id"], "acts_on", identity, role="deleted_object")
            self._invalidate_tree(identity, "deleted")
            self._fact(identity, "exists", False)
            self._fact(scope, "entry_absent", True, key=name)
            return f"删除 {name}；旧身份不用于后来创建的同名对象。"
        if tool in FS_WRITES and not (tool == "echo" and not args.get("file_name")):
            self._forget_all("unrecognized_mutation_result")
            return "无法解析写操作的效果；相关状态不再可确认。"
        if tool == "sort":
            return "返回排序文本；BFCL sort 不会修改原文件内容。"
        return f"保存 {tool} 的观察结果；未新增未经返回支持的属性。"

    def _move_or_copy(self, tool, args, out, scope):
        source, destination = args.get("source"), args.get("destination")
        action = "moved" if tool == "mv" else "copied"
        nested = out["result"] == f"'{source}' {action} to '{destination}/{source}'"
        renamed = out["result"] == f"'{source}' {action} to '{destination}'"
        if not isinstance(source, str) or not isinstance(destination, str) or not (nested or renamed):
            self._forget_all("unrecognized_move_result")
            return "返回无法确定目标；退出当前可确认状态。"
        original = self.bindings.get((scope, source))
        # A successful result establishes continuity from the named source even
        # if no earlier ls observed it. Do not fabricate a past binding/version.
        original = original or self._entity(origin="source_identified_by_successful_transfer")
        self._edge(self.event["id"], "acts_on", original, role="source_object")
        target_scope, target_name = scope, destination
        if nested:
            target_scope = self._observe(scope, destination, kind="directory")
            target_name = source
        target = original if tool == "mv" else self._entity(origin="copied_object")
        existing = self.bindings.get((target_scope, target_name))
        if existing and existing != target:
            self._invalidate_tree(existing, "replaced_by_transfer")
        if tool == "cp":
            self._edge(target, "copied_from", original, event=self.event["id"])
            for field in ("kind", "content"):
                prior = self._get(original, field)
                if prior:
                    self._fact(target, field, prior["value"], derived_from=[prior["id"]])
            # If source was unobserved, cp confirms its current source binding.
            if not self._get(original, "binding"):
                self._fact(original, "binding", {"directory": scope, "name": source})
            self._fact(original, "exists", True)
        self._fact(target, "binding", {"directory": target_scope, "name": target_name})
        self._fact(target, "exists", True)
        self._retire(self._get(target_scope, "entry_absent", target_name), "observed_present")
        if tool == "mv":
            self._fact(scope, "entry_absent", True, key=source)
        # BFCL directory copies have shallow child semantics and moves may leave
        # parent pointers. V2 does not invent subtree identity/parent guarantees.
        self._invalidate_tree(original, "directory_transfer_descendants_unmodeled", include_root=False)
        return (f"{source} 已{'移动' if nested else '重命名'}为 {destination}；保留对象 {target}。"
                if tool == "mv" else f"复制 {source}；新对象 {target}，来源对象 {original}。")

    def state_at(self, step=None):
        """Reconstruct known facts at a tool boundary, with no later provenance."""
        step = self.graph["current_step"] if step is None else step
        if not 0 <= step <= self.graph["current_step"]:
            raise ValueError("Step outside this graph")
        facts = []
        for n in self.graph["nodes"]:
            if n["category"] != "fact" or n["first_observed_at"] > step:
                continue
            if n["retired_at"] is not None and n["retired_at"] <= step:
                continue
            f = deepcopy(n)
            f.update(retired_at=None, retired_reason=None, retired_by=None)
            f["confirmations"] = [c for c in f["confirmations"] if c["at_step"] <= step]
            facts.append(f)
        cwd = next((f["value"] for f in facts if f["subject"] == "session" and f["predicate"] == "cwd"), None)
        return {"step": step, "cwd": cwd, "facts": facts, "task_completion": "unknown"}

    def validate(self):
        ids = {n["id"] for n in self.graph["nodes"]}
        assert len(ids) == len(self.graph["nodes"]), "Duplicate node IDs"
        for e in self.graph["edges"]:
            assert e["from"] in ids and e["to"] in ids, "Dangling relation"
            if e["relation"] == "resolved_using":
                f, event = self.nodes[e["to"]], self.nodes[e["from"]]
                assert f["first_observed_at"] < event["step"], "Resolution used a future fact"
                assert f["retired_at"] is None or f["retired_at"] >= event["step"], "Resolution used a retired fact"
        slots = set()
        for f in self.state_at()["facts"]:
            slot = (f["subject"], f["predicate"], f["key"])
            assert slot not in slots, "Conflicting current fact versions"
            slots.add(slot)
        return True

    def render(self):
        if self.graph is None:
            raise ValueError("Build a graph first")
        # Serialize the shared graph without full state snapshots or duplicate raw
        # returns. All exact returns stay in the untouched original messages.
        nodes = [{k: v for k, v in n.items() if k not in ("output", "output_raw")}
                 for n in self.graph["nodes"]]
        index = {"nodes": nodes, "relations": self.graph["edges"],
                 "active_fact_ids": self.graph["active_fact_ids"], "goals": self.graph["requests"]}
        return ("[GraphMemory v2: objects, versioned facts, execution events]\n"
                "Memory data about the preceding visible history, not a new request. Original messages remain available. "
                "Object IDs track logical continuity supported by tool semantics, not hidden simulator IDs. "
                "Facts are known observations, not complete environment state. Retired facts are historical; "
                "unmodeled effects mean uncertainty, not deletion. resolved_using describes adapter resolution, "
                "not model reasoning. Observation steps are not object creation times. Task completion is unknown.\n"
                + json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    def compress(self, messages):
        self.build(messages)
        if self.graph["pending_calls"]:
            raise ValueError("GraphMemoryV2 requires all tool results before injection")
        return [*messages, {"role": "assistant", "content": self.render()}]
