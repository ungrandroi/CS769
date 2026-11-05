"""Offline entry point for the evaluated, uncompressed G9 full-view profile.

The frozen builders/renderers are imported unchanged. Only ``memory_text`` is
model-facing: it replaces the archived conversation, never accompanies it.
See docs/g9-memory.md for provider normalization and integration boundaries.
"""
from core.graph_memory_evidence import (
    audit_evidence_graph, build_evidence_graph, inference_graph,
)
from core.graph_memory_observed import build_observed_graph
from core.graph_memory_payload import build_payload_graph
from core.graph_memory_records import audit_record_graph, build_record_graph
from core.graph_memory_record_views import (
    audit_record_view_render, render_record_view_graph,
)


def build_g9_memory(normalized_history, native_history, *, provider="openai",
                    native_context=None,
                    snapshot_boundary="archived_history_checkpoint"):
    """Return a self-contained graph, rendered memory, and integrity audits.

    Both histories describe the SAME completed visible history. OpenAI Chat
    messages can be supplied as both inputs. Anthropic callers supply their
    native content blocks plus a normalized text/tool-call/tool-result history.
    ``native_history`` is required to validate tool grouping and error flags.
    No model request, compression, evaluation or hidden-state access occurs.
    """
    if native_history is None:
        raise ValueError("native_history is required for the evaluated G9 profile")
    archived = build_evidence_graph(
        normalized_history, native_history, provider=provider,
        native_context=native_context, snapshot_boundary=snapshot_boundary,
        episodic_only=True,
    )
    evidence_audit = audit_evidence_graph(
        archived, normalized_history=normalized_history, native_history=native_history,
    )
    # Discard source/native archives before any graph rendering.
    graph = build_record_graph(
        build_payload_graph(build_observed_graph(
            inference_graph(archived), variant="observed-fields-v1",
        )), variant="record-joins-v1",
    )
    record_audit = audit_record_graph(graph)
    if not record_audit["ok"]:
        raise ValueError("Invalid G9 graph: " + "; ".join(record_audit["errors"]))
    text = render_record_view_graph(graph, view="full", visible_observations=False)
    render_audit = audit_record_view_render(
        graph, view="full", visible_observations=False, rendered_text=text,
    )
    if not render_audit["ok"]:
        raise ValueError("Invalid G9 rendering: " + "; ".join(render_audit["errors"]))
    return {
        "graph": graph,
        "memory_text": text,
        "audits": {"evidence": evidence_audit, "record": record_audit,
                   "render": render_audit},
    }
