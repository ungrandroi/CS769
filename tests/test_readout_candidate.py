from copy import deepcopy

import pytest

from core.diagnostic_views import state_index
from core.readout_candidate import compact_event_index, expand_event_index


def graph():
    return {
        "method": "v2-compact",
        "fact_columns": ["subject", "predicate", "value", "retired_at", "fact_scope", "key"],
        "facts": {
            "f/0~": ["o1", "location", None, None, "state", None],
            "f1": ["o1", "location", "elsewhere", None, "state", None],
            "f2": ["o1", "listed", True, None, "observation", None],
            "f3": ["o1", "location", "old", 2, "state", None],
            "f4": ["o2", "size", 0, None, "state", "bytes"],
        },
        "active_facts": ["f/0~", "f1", "f2", "f4"],
    }


def test_index_preserves_unknown_alternatives_types_and_sources():
    source = graph()
    before = deepcopy(source)
    view, audit = compact_event_index(source)
    assert view["active_state_index"]["fact_ids"] == [["f/0~", "f1"], ["f4"]]
    assert audit["ambiguous_entries"] == 1
    assert expand_event_index(view, source) == state_index(source)["view"]
    assert source == before


@pytest.mark.parametrize("groups", [[], [["f1"]], [["f3"]], [["f2"]],
    [["missing"]], [["f/0~", "f1", "f1"], ["f4"]],
    [["f/0~", "f1", "f4"]], [["f1", "f/0~"], ["f4"]]])
def test_rejects_missing_stale_observed_duplicate_or_changed_groups(groups):
    source = graph()
    view, _ = compact_event_index(source)
    view["active_state_index"]["fact_ids"] = groups
    with pytest.raises(ValueError):
        expand_event_index(view, source)


def test_no_state_entries_remain_empty():
    source = graph()
    source["active_facts"] = ["f2"]
    view, audit = compact_event_index(source)
    assert audit["eligible_entries"] == 0
    assert expand_event_index(view, source) == {"state_index": []}


def test_contradictory_validity_is_rejected():
    source = graph()
    source["active_facts"].append("f3")
    with pytest.raises(ValueError):
        compact_event_index(source)
