"""Offline second-round readout candidates; no pruning or semantic inference.

All original graph fields and source messages remain in their frozen codec.
Only Event gets a compact form of the previously tested active-state index.
State and Dedup retain the minimal, unaugmented representation as controls.
"""
from copy import deepcopy

from core import lossless_event, lossless_state
from core.diagnostic_views import state_index
from core.optimized_graph import MINIMAL, _same, dumps, restore_history

VERSION = "readout-candidate-v1"
FORMATS = {
    "state": ("v1-compact", "state-shared-v1", lossless_state),
    "event": ("v2-compact", "lossless-event/tables-v1", lossless_event),
    "dedup": ("v2-dedup", "lossless-event/shared-v1", lossless_event),
}


def _escape(value):
    return value.replace("~", "~0").replace("/", "~1")


def compact_event_index(graph):
    if graph.get("method") not in ("v2-compact", "v2-dedup"):
        raise ValueError("Fact index requires an Event graph")
    original = state_index(graph)
    groups = []
    for entry in original["view"]["state_index"]:
        ids = []
        for pointer in entry["fact_refs"]:
            parts = pointer.split("/")
            if len(parts) != 3 or parts[1] != "facts":
                raise ValueError("Unexpected fact pointer")
            ids.append(parts[2].replace("~1", "/").replace("~0", "~"))
        groups.append(ids)
    view = {"active_state_index": {"group_by": ["subject", "predicate", "key"],
                                   "fact_ids": groups}}
    if not _same(expand_event_index(view, graph), original["view"]):
        raise AssertionError("Compact index did not restore the original index")
    return view, deepcopy(original["audit"])


def expand_event_index(view, graph):
    """Recover every original index pointer, including unresolved alternatives."""
    if set(view) != {"active_state_index"}:
        raise ValueError("Unknown index envelope")
    packed = view["active_state_index"]
    if (set(packed) != {"group_by", "fact_ids"}
            or packed["group_by"] != ["subject", "predicate", "key"]
            or not isinstance(packed["fact_ids"], list)):
        raise ValueError("Unknown grouping schema")
    columns = graph["fact_columns"]
    result = []
    for ids in packed["fact_ids"]:
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
            raise ValueError("Expected nonempty list of fact IDs")
        if any(i not in graph["facts"] for i in ids):
            raise ValueError("Unknown fact ID")
        head = "/facts/" + _escape(ids[0])
        entry = {"subject_ref": head + "/" + str(columns.index("subject")),
                 "field_ref": head + "/" + str(columns.index("predicate"))}
        if "key" in columns:
            entry["key_ref"] = head + "/" + str(columns.index("key"))
        entry["fact_refs"] = ["/facts/" + _escape(i) for i in ids]
        result.append(entry)
    unpacked = {"state_index": result}
    # Reject omissions, stale facts, merged groups, added observations, duplicates,
    # or reordered alternatives. Do not infer new validity from matching values.
    if not _same(unpacked, state_index(graph)["view"]):
        raise ValueError("Index differs from existing eligible state facts")
    return unpacked


def prepare(history, metadata, method, *, event_index=False):
    graph_method, encoding, codec = FORMATS[method]
    graph, encoded = metadata["graph"], metadata["encoded"]
    if graph.get("method") != graph_method or encoded.get("encoding") != encoding:
        raise ValueError("Unexpected frozen representation")
    if not _same(codec.decode(encoded), graph):
        raise ValueError("Source graph fails typed restoration")
    working = [m for m in history if m.get("role") not in ("system", "developer")]
    if not _same(restore_history(graph), working):
        raise ValueError("Source history differs from checkpoint")
    body = dumps(encoded)
    text = MINIMAL + "\n" + body
    view, index_audit = None, None
    if event_index:
        if method != "event":
            raise ValueError("This candidate enables an index only for Event")
        view, index_audit = compact_event_index(graph)
        if index_audit["eligible_entries"]:
            text += "\n" + dumps(view)
        else:
            view = None
    return [{"role": "user", "content": text}], {
        "version": VERSION, "method": method,
        "candidate": "compact-state-index" if event_index else "minimal-base-control",
        "instruction": MINIMAL, "body": body, "view": view,
        "index_audit": index_audit, "typed_graph_restoration": True,
        "source_history_restoration": True, "semantic_editing": False,
        "goal_copies_added": 0, "diagnostic_prose_added": False,
    }
