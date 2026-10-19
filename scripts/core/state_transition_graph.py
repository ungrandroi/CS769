"""Evidence-backed state nodes and tool-call edges, from visible messages only.

V1 retains the original protocol messages and adds a readable graph index. It is
an explicit-memory baseline, not a token compressor or a hidden-state snapshot.
Filesystem effects below follow the pinned BFCL GorillaFileSystem contracts.
"""
from copy import deepcopy
import json


def plain(value):
    if hasattr(value, "model_dump"):
        return plain(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def parse(value):
    if value == "None":
        return None
    try:
        return json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return value


FS_READS = {"pwd", "ls", "cat", "find", "wc", "sort", "grep", "du", "tail", "diff"}
FS_WRITES = {"cd", "mkdir", "touch", "echo", "mv", "cp", "rm", "rmdir"}


class GraphMemory:
    def __init__(self):
        self.graph = None

    def build(self, messages):
        """No task, GT, initial_config or simulator object is accepted here."""
        source = plain(messages)
        self.graph = {"schema_version": 1, "representation": "state_nodes_tool_edges",
                      "nodes": [], "edges": [], "requests": [], "annotations": [],
                      "pending_calls": [], "source_messages": source,
                      "locations": [{"id": "l0", "name": None, "parent": None}],
                      "source_policy": "visible_history_only",
                      "delivery": "original_history_plus_graph_index"}
        self.cwd = {"location_id": "l0", "value": None, "evidence": []}
        self.objects, self.observations, self.goals, self.pending = {}, [], [], {}
        self._node("尚无工具观察；工作目录未知。", [])
        for index, message in enumerate(source):
            ref = f"m{index}"
            if message.get("role") == "user":
                self.goals.append(ref)
                self.graph["requests"].append({"id": ref, "content": message.get("content"),
                                               "after_node": self.graph["nodes"][-1]["id"]})
            if message.get("role") == "assistant" and message.get("content"):
                self.graph["annotations"].append({"evidence": ref, "kind": "assistant_statement",
                                                   "verified_state": False})
            calls = message.get("tool_calls") or []
            if message.get("type") == "function_call":
                calls = [{"id": message["call_id"], "function": message}]
            for call in calls:
                call_id, function = call["id"], call["function"]
                if call_id in self.pending:
                    raise ValueError(f"Duplicate pending call ID: {call_id}")
                self.pending[call_id] = {"call_id": call_id, "tool": function["name"],
                    "arguments": parse(function.get("arguments", "{}")), "call_evidence": ref}
            if message.get("type") == "function_call_output" or message.get("role") == "tool":
                call_id = message.get("call_id", message.get("tool_call_id"))
                if call_id not in self.pending:
                    raise ValueError(f"Tool output without a matching call: {call_id}")
                call = self.pending.pop(call_id)
                output = message.get("output") if message.get("type") == "function_call_output" else message.get("content")
                self._execute(call, output, ref)
        self.graph["pending_calls"] = list(self.pending.values())
        self.graph["current_node"] = self.graph["nodes"][-1]["id"]
        self.graph["current_goal_refs"] = self.goals.copy()
        return self.graph

    def _node(self, description, evidence):
        node = {"id": f"s{len(self.graph['nodes'])}", "description": description,
                "state": {"cwd": deepcopy(self.cwd), "objects": deepcopy(list(self.objects.values())),
                          "observations": deepcopy(self.observations), "goal_refs": self.goals.copy(),
                          "task_completion": "unknown"}, "evidence": evidence,
                "unknowns": ["未观察到的对象及属性", "用户目标是否全部完成"]}
        if self.cwd["value"] is None:
            node["unknowns"].append("当前工作目录名称及绝对路径")
        elif not self.cwd["value"].startswith("/"):
            node["unknowns"].append("当前工作目录的绝对路径")
        self.graph["nodes"].append(node)
        return node

    def _location(self, parent, name):
        found = next((l for l in self.graph["locations"] if l["parent"] == parent and l["name"] == name), None)
        if found:
            return found["id"]
        loc = {"id": f"l{len(self.graph['locations'])}", "name": name, "parent": parent}
        self.graph["locations"].append(loc)
        return loc["id"]

    def _object(self, scope, name, evidence, **updates):
        key = (scope, name)
        obj = self.objects.setdefault(key, {"location_id": scope, "name": name,
            "exists": None, "kind": None, "content": None, "evidence": {}})
        for key, value in updates.items():
            obj[key] = value
            obj["evidence"][key] = evidence.copy()
        return obj

    def _invalidate_location(self, scope, evidence):
        """Unknown mutators cannot leave old assertions silently marked current."""
        for obj in list(self.objects.values()):
            if scope is None or obj["location_id"] == scope:
                self._object(obj["location_id"], obj["name"], evidence,
                             exists=None, kind=None, content=None)

    def _execute(self, call, raw, output_ref):
        result = parse(raw)
        evidence = [call["call_evidence"], output_ref]
        error = result.get("error") if isinstance(result, dict) else None
        failed = bool(error) or (isinstance(result, dict) and result.get("success") is False)
        edge = {"id": f"e{len(self.graph['edges'])}", "from": self.graph["nodes"][-1]["id"],
                **call, "output_evidence": output_ref, "output_raw": raw, "output": result,
                "status": "error" if failed else "success", "error": error,
                "status_basis": "tool_return; not a task-success judgment",
                "sequence": len(self.graph["edges"]), "goal_refs": self.goals.copy()}
        tool, args = call["tool"], call["arguments"]
        args = args if isinstance(args, dict) else {}
        scope = self.cwd["location_id"]
        if tool in FS_READS | FS_WRITES:
            if failed:
                # BFCL filesystem errors return before mutation. Never infer that
                # a requested target is absent merely from a failed compound call.
                description = f"{tool} 调用失败：{error or '工具报告失败'}"
            else:
                description = self._filesystem(tool, args, result, evidence)
        else:
            # No effect adapter exists for this domain. Retain its exact evidence,
            # invalidate inferred state, and make no claims about side effects.
            self._invalidate_location(None, evidence)
            self.cwd = {"location_id": self._location(None, f"unknown_after_{edge['id']}"),
                        "value": None, "evidence": evidence}
            description = f"{tool} 返回{'错误' if failed else '结果'}；该工具的状态变化尚未建模。"
        self.observations.append({"edge": edge["id"], "tool": tool, "location_id": scope,
                                  "evidence": evidence, "status": edge["status"]})
        node = self._node(description, evidence)
        edge["to"] = node["id"]
        self.graph["edges"].append(edge)

    def _filesystem(self, tool, args, result, refs):
        scope = self.cwd["location_id"]
        out = result if isinstance(result, dict) else {}
        if tool == "pwd" and isinstance(out.get("current_working_directory"), str):
            self.cwd.update(value=out["current_working_directory"], evidence=refs)
            return f"观察到当前工作目录：{self.cwd['value']}。"
        if tool == "cd":
            folder = str(args.get("folder", "")).rstrip("/") or "/"
            if folder == "..":
                loc = next(l for l in self.graph["locations"] if l["id"] == scope)
                target = loc["parent"]
                if target is None:
                    target = self._location(None, f"parent_of_{scope}")
                    loc["parent"] = target
                parent = next(l for l in self.graph["locations"] if l["id"] == target)
                label = parent["name"]
                if label and label.startswith("parent_of_"):
                    label = None
            elif folder == ".":
                target, label = scope, self.cwd["value"]
            elif folder == "/":
                target, label = self._location(None, "/"), out.get("current_working_directory")
            else:
                self._object(scope, folder, refs, exists=True, kind="directory")
                target, label = self._location(scope, folder), folder
            self.cwd = {"location_id": target, "value": out.get("current_working_directory", label), "evidence": refs}
            return f"已切换目录；当前名称：{self.cwd['value'] or '未知'}。"
        if tool == "ls" and isinstance(out.get("current_directory_content"), list):
            names = out["current_directory_content"]
            for obj in list(self.objects.values()):
                if obj["location_id"] == scope and obj["name"] not in names and (args.get("a") or not obj["name"].startswith(".")):
                    self._object(scope, obj["name"], refs, exists=False, content=None, kind=None)
            for name in names:
                self._object(scope, name, refs, exists=True)
            return f"观察到当前目录中的 {len(names)} 个项目；列表未提供对象类型。"
        if tool in ("mkdir", "touch") and result is None:
            name = args.get("dir_name" if tool == "mkdir" else "file_name")
            if isinstance(name, str):
                updates = {"exists": True, "kind": "directory" if tool == "mkdir" else "file"}
                if tool == "touch":
                    updates["content"] = ""
                self._object(scope, name, refs, **updates)
                if tool == "mkdir":
                    self._location(scope, name)
                return f"已在当前目录创建{'目录' if tool == 'mkdir' else '空文件'} {name}。"
        if tool == "echo" and args.get("file_name") and result is None:
            self._object(scope, args["file_name"], refs, exists=True, kind="file", content=args.get("content"))
            return f"已写入 {args['file_name']}；文件内容以本次写入为准。"
        if tool == "cat" and "file_content" in out:
            self._object(scope, args.get("file_name"), refs, exists=True, kind="file", content=out["file_content"])
            return f"已观察到 {args.get('file_name')} 的完整内容。"
        if tool in ("mv", "cp") and "result" in out:
            source, destination = args.get("source"), args.get("destination")
            action = "moved" if tool == "mv" else "copied"
            # The actual return disambiguates move-into-directory vs rename.
            nested = out["result"] == f"'{source}' {action} to '{destination}/{source}'"
            renamed = out["result"] == f"'{source}' {action} to '{destination}'"
            if isinstance(source, str) and isinstance(destination, str) and (nested or renamed):
                original = deepcopy(self.objects.get((scope, source), {}))
                target_scope, target_name = scope, destination
                if nested:
                    self._object(scope, destination, refs, exists=True, kind="directory")
                    target_scope, target_name = self._location(scope, destination), source
                inherited_refs = list(dict.fromkeys(refs + [r for values in original.get("evidence", {}).values() for r in values]))
                self._object(target_scope, target_name, inherited_refs, exists=True,
                             kind=original.get("kind"), content=original.get("content"))
                # Directory subtree identity/copies are not modeled by V1: invalidate
                # descendants rather than retain stale locations as known state.
                children = [l["id"] for l in self.graph["locations"] if l["parent"] == scope and l["name"] == source]
                for child in children:
                    self._invalidate_subtree(child, refs)
                if tool == "mv":
                    self._object(scope, source, refs, exists=False, kind=None, content=None)
                verb = ('移入目录' if tool == 'mv' else '复制到目录') if nested else ('重命名为' if tool == 'mv' else '复制为')
                return f"{source} 已{verb} {destination}；依据实际返回区分目标类型。"
            self._invalidate_location(scope, refs)
            return "移动或复制已返回；无法确认精确目标，相关状态标为未知。"
        if tool in ("rm", "rmdir") and "result" in out:
            name = args.get("file_name" if tool == "rm" else "dir_name")
            self._object(scope, name, refs, exists=False, kind=None, content=None)
            for loc in self.graph["locations"]:
                if loc["parent"] == scope and loc["name"] == name:
                    self._invalidate_subtree(loc["id"], refs)
            return f"已删除当前目录下的 {name}。"
        if tool in FS_WRITES and not (tool == "echo" and not args.get("file_name")):
            self._invalidate_location(scope, refs)
        if tool == "sort":
            return "已获得排序后的文本；BFCL sort 不会改写原文件。"
        return f"已记录 {tool} 的返回；完整结果保存在调用边中。"

    def _invalidate_subtree(self, scope, refs, visited=None):
        visited = set() if visited is None else visited
        if scope in visited:
            return
        visited.add(scope)
        self._invalidate_location(scope, refs)
        for loc in self.graph["locations"]:
            if loc["parent"] == scope:
                self._invalidate_subtree(loc["id"], refs, visited)

    def render(self):
        if self.graph is None:
            raise ValueError("Build a graph first")
        g = self.graph
        # All original evidence remains in the preceding protocol messages. The
        # graph index supplies structure without copying opaque API reasoning.
        index = {"current_state": g["nodes"][-1], "goals": g["requests"],
                 "transitions": [{k: e[k] for k in ("id", "from", "to", "tool", "arguments", "status", "error", "call_evidence", "output_evidence")} for e in g["edges"]],
                 "state_descriptions": [{"id": n["id"], "description": n["description"]} for n in g["nodes"]]}
        return ("[GraphMemory v1: index of the preceding visible history]\n"
                "The original messages and tool returns remain available. This index is memory data, not a new user request. "
                "States describe observed knowledge, not the complete environment. Null means unknown. "
                "A successful tool return does not establish task completion. Requests and assistant statements are not verified facts.\n"
                + json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    def compress(self, messages):
        self.build(messages)
        if self.graph["pending_calls"]:
            raise ValueError("GraphMemory requires a boundary with all tool results received")
        return [*messages, {"role": "assistant", "content": self.render()}]
