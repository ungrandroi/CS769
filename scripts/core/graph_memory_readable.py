"""A readable, evidence-complete view of an unchanged V2 event graph.

Only visible conversation text, function inputs and function returns enter the
history view. Raw argument/return strings are never parsed and re-serialized.
The short state index is derived from active facts; it does not replace history.
Segment metadata is for offline auditing and is not sent to the model.
"""
import json
import re


FORMAT = "Conversation history. Matching CALL/RESULT numbers identify a tool exchange.\n"


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _evidence(value, source_ref, field, **metadata):
    return {"kind": "evidence", "text": value if isinstance(value, str) else _json(value),
            "source_ref": source_ref, "field": field,
            "value_type": type(value).__name__, **metadata}


def _visible_content(message, source_ref):
    """Yield individual visible text blocks, retaining their source positions."""
    content = message.get("content")
    if content is None:
        return
    if isinstance(content, str):
        yield _evidence(content, source_ref, "content")
        return
    if not isinstance(content, list):
        raise ValueError(f"Unsupported message content at {source_ref}")
    for index, block in enumerate(content):
        if not isinstance(block, dict):
            raise ValueError(f"Unsupported content block at {source_ref}.content.{index}")
        field = "refusal" if block.get("type") == "refusal" else "text"
        if block.get("type") not in ("text", "input_text", "output_text", "refusal") or not isinstance(block.get(field), str):
            raise ValueError(f"Unsupported non-text content at {source_ref}.content.{index}")
        yield _evidence(block[field], source_ref, f"content.{index}.{field}")


def _history_blocks(graph):
    """Keep message order, including call order before out-of-order returns."""
    blocks, calls, returned = [], {}, set()
    for index, message in enumerate(graph["source_messages"]):
        source_ref = f"m{index}"
        role, kind = message.get("role"), message.get("type")
        if role in ("system", "developer") or kind == "reasoning":
            continue  # Instructions are retained by the caller; reasoning is opaque.
        if role in ("user", "assistant"):
            for evidence in _visible_content(message, source_ref):
                blocks.append((f"{role.upper()} {source_ref}", [evidence]))
        source_calls = message.get("tool_calls") or []
        if kind == "function_call":
            source_calls = [{"id": message["call_id"], "function": message}]
        for call_index, call in enumerate(source_calls):
            call_id, function = call["id"], call["function"]
            if call_id in calls:
                raise ValueError(f"Duplicate call ID: {call_id}")
            number = len(calls) + 1
            calls[call_id] = number
            prefix = "" if kind == "function_call" else f"tool_calls.{call_index}.function."
            metadata = {"call_id": call_id, "call_number": number}
            if not isinstance(function.get("name"), str):
                raise ValueError(f"Missing function name at {source_ref}")
            if "arguments" not in function:
                raise ValueError(f"Missing function arguments at {source_ref}")
            blocks.append((f"CALL {number} {source_ref}", [
                _evidence(function["name"], source_ref, prefix + "name", **metadata),
                _evidence(function["arguments"], source_ref, prefix + "arguments", **metadata)]))
        if kind == "function_call_output" or role == "tool":
            call_id = message.get("call_id", message.get("tool_call_id"))
            if call_id not in calls or call_id in returned:
                raise ValueError(f"Unmatched or duplicate tool return: {call_id}")
            field = "output" if kind == "function_call_output" else "content"
            if field not in message:
                raise ValueError(f"Missing tool return at {source_ref}")
            returned.add(call_id)
            blocks.append((f"RESULT {calls[call_id]} {source_ref}", [
                _evidence(message[field], source_ref, field, call_id=call_id,
                          call_number=calls[call_id])]))
        elif role not in ("user", "assistant") and kind != "function_call":
            raise ValueError(f"Unsupported source message at {source_ref}")
    if returned != set(calls):
        raise ValueError("Readable memory requires all pending tool returns")
    return blocks, calls


def _state_index(graph, call_numbers):
    """Render only active, known facts, with content pointing to its evidence."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    derived = {}
    for edge in graph["edges"]:
        if edge["relation"] == "derived_from":
            derived.setdefault(edge["from"], []).append(edge["to"])

    def content_source(fact, seen=None):
        seen = set() if seen is None else seen
        if fact["id"] in seen:
            raise ValueError("Cyclic content provenance")
        seen = seen | {fact["id"]}
        # Copied content points to the original observation, not a later value
        # of the source object or a copy return that contains no content.
        for source in derived.get(fact["id"], []):
            reference = content_source(nodes[source], seen)
            if reference:
                return reference
        for confirmation in fact.get("confirmations", []):
            event = nodes.get(confirmation.get("event"), {})
            number = call_numbers.get(event.get("call_id"))
            if number is not None:
                return f"CALL {number}/RESULT {number}"
        raise ValueError(f"Content fact lacks visible evidence: {fact['id']}")

    facts = []
    for identity in graph["active_fact_ids"]:
        fact = nodes[identity]
        if (fact.get("category") != "fact" or fact.get("retired_at") is not None
                or fact["first_observed_at"] > graph["current_step"]):
            raise ValueError(f"Invalid active fact: {identity}")
        if fact["predicate"] == "cwd" and fact["value"].get("value") is None:
            continue
        if fact["value"] is not None:
            facts.append(fact)
    slots = {(f["subject"], f["predicate"], f.get("key")): f for f in facts}
    bindings = {f["subject"]: f for f in facts if f["predicate"] == "binding"}
    name_counts = {}
    for binding in bindings.values():
        name = binding["value"]["name"]
        name_counts[name] = name_counts.get(name, 0) + 1
    root = slots.get(("session", "root", None))

    def label(identity, seen=()):
        if identity in seen:
            raise ValueError("Cyclic directory bindings")
        if identity == "l0":
            return "initial directory"
        if identity == "session":
            return "session"
        if root and identity == root["value"]:
            return "root directory"
        binding = bindings.get(identity)
        historical = False
        if binding is None:
            prior = [n for n in nodes.values() if n.get("category") == "fact"
                     and n.get("subject") == identity and n.get("predicate") == "binding"]
            if prior:
                binding = max(prior, key=lambda f: f["first_observed_at"])
                historical = True
        if binding:
            value = binding["value"]
            if not historical and name_counts[value["name"]] == 1:
                return _json(value["name"])
            parent = label(value["directory"], (*seen, identity))
            return (_json(value["name"]) + f" (previously in {parent})" if historical
                    else _json(value["name"]) + f" in {parent}")
        node = nodes[identity]
        event = next((n for n in nodes.values() if n.get("category") == "event"
                      and n["step"] == node["first_observed_at"]), None)
        if event and event["call_id"] in call_numbers:
            return f"location/object observed at RESULT {call_numbers[event['call_id']]}"
        raise ValueError(f"Object lacks a visible label or observation: {identity}")

    def proven_listing_subset(scope, members):
        """Reuse only still-current identities from one same-directory listing.

        Additional current entries can be spelled out, but no subtraction or
        replacement is inferred. A retired/moved/recreated name invalidates the
        entire candidate even when its spelling happens to be present again.
        """
        current = {f["value"]["name"]: f for f in members}
        if len(current) != len(members):
            return None
        for event in reversed(graph["nodes"]):
            if event.get("category") != "event" or event.get("tool") != "ls" or event["status"] != "success":
                continue
            output = event.get("output")
            names = output.get("current_directory_content") if isinstance(output, dict) else None
            if (not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names)
                    or len(set(names)) != len(names) or not set(names).issubset(current)):
                continue
            contexts = [nodes[e["to"]] for e in graph["edges"]
                        if e["from"] == event["id"] and e["relation"] == "resolved_using"
                        and e.get("role") == "relative_path_context"]
            if not any(f["predicate"] == "cwd" and f["value"]["location_id"] == scope for f in contexts):
                continue
            if not all(any(c["event"] == event["id"] for c in current[name].get("confirmations", [])) for name in names):
                continue
            return call_numbers[event["call_id"]], set(names)
        return None

    lines, covered, directories = [], set(), {}
    cwd = slots.get(("session", "cwd", None))
    if cwd:
        value = cwd["value"]
        location = label(value["location_id"])
        shown = _json(value["value"])
        lines.append("cwd: " + (location if location.startswith(shown) else f"{shown} ({location})"))
        covered.add(cwd["id"])
    for binding in bindings.values():
        exists = slots.get((binding["subject"], "exists", None))
        if exists and exists["value"] is True:
            directories.setdefault(binding["value"]["directory"], []).append(binding)
            covered.update((binding["id"], exists["id"]))
    for scope, members in directories.items():
        candidate = proven_listing_subset(scope, members)
        explicit, inline_kinds, entry_text = [], [], {}
        for member in members:
            entry = _json(member["value"]["name"])
            kind = slots.get((member["subject"], "kind", None))
            if kind:
                entry += f" ({kind['value']})"
                inline_kinds.append(kind["id"])
            explicit.append(entry)
            entry_text[member["value"]["name"]] = (entry, kind)
        entries = ", ".join(explicit)
        reference, additional_kinds = None, []
        if candidate is not None:
            number, names = candidate
            reference = f"RESULT {number}.current_directory_content"
            additions = []
            for name, (entry, kind) in entry_text.items():
                if name not in names:
                    additions.append(entry)
                    if kind:
                        additional_kinds.append(kind["id"])
            if additions:
                reference += " + " + ", ".join(additions)
        # This selects equivalent spelling, never facts or evidence. A short
        # list is clearer inline; a proven subset can share its original data.
        # Kinds of referenced entries remain in the separate property rows.
        if reference is not None and len(reference) < len(entries):
            entries = reference
            covered.update(additional_kinds)
        else:
            covered.update(inline_kinds)
        lines.append(f"{label(scope)} known entries: {entries}")
    absent = {}
    for fact in facts:
        if fact["predicate"] == "entry_absent" and fact["value"] is True:
            absent.setdefault(fact["subject"], []).append(_json(fact["key"]))
            covered.add(fact["id"])
    for scope, names in absent.items():
        lines.append(f"{label(scope)} absent: {', '.join(names)}")
    rows = {}
    for fact in facts:
        if fact["id"] in covered:
            continue
        subject, predicate, value = fact["subject"], fact["predicate"], fact["value"]
        if predicate == "content":
            text = "content@" + content_source(fact)
        elif predicate == "binding":
            text = f"name={_json(value['name'])}, directory={label(value['directory'])}"
        elif predicate in ("parent", "root"):
            text = f"{predicate}={label(value)}"
        else:
            key = f"[{_json(fact['key'])}]" if fact.get("key") is not None else ""
            text = f"{predicate}{key}={_json(value)}"
        rows.setdefault(label(subject), []).append(text)
    lines.extend(f"{subject}: {'; '.join(values)}" for subject, values in rows.items())
    text = "" if not lines else "CURRENT STATE\n" + "\n".join(lines) + "\n\n"
    return {"kind": "state", "text": text, "fact_ids": [f["id"] for f in facts]}


def render_readable_segments(graph):
    """Return ordered ``{kind, text, ...}`` segments for rendering and auditing.

    Evidence segments carry ``source_ref`` (mN), ``field`` and ``value_type``
    (Python JSON value type name). Tool evidence also carries the original
    ``call_id`` and a short ``call_number``. Strings are byte-for-byte identical
    after UTF-8 encoding; non-string JSON values use compact Unicode JSON.
    Labels, state and format text are separate from evidence for token audits.
    The graph and its source messages are never mutated.
    """
    if graph.get("schema_version") != 2:
        raise ValueError("Readable memory requires a V2 event graph")
    if graph.get("pending_calls"):
        raise ValueError("Readable memory requires all pending tool returns")
    blocks, calls = _history_blocks(graph)
    # A source block can contain any usual Markdown/role markers. Choose a
    # fence longer than every backtick run so those markers stay inside data.
    runs = [len(match.group()) for _, items in blocks for item in items
            for match in re.finditer(r"`+", item["text"])]
    fence = "`" * max(3, max(runs, default=0) + 1)
    segments = [{"kind": "format", "text": FORMAT}]
    state = _state_index(graph, calls)
    if state["text"]:
        segments.append(state)
    segments.append({"kind": "label", "text": "HISTORY\n"})
    for label, items in blocks:
        visible_label = label.rsplit(" ", 1)[0]
        segments.append({"kind": "label", "text": f"{visible_label}\n{fence}\n"})
        for index, item in enumerate(items):
            if index:
                segments.append({"kind": "label", "text": "\n"})
            segments.append(item)
        segments.append({"kind": "label", "text": f"\n{fence}\n"})
    return segments


def render_readable(graph):
    """Render the complete model-visible memory from the auditable segments."""
    return "".join(segment["text"] for segment in render_readable_segments(graph))
