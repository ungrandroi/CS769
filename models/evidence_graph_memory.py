"""Public evaluated evidence graph profile; uses the same builder as the CLI."""
def build_evidence_graph_memory(normalized_history,native_history,*,provider="openai",native_context=None,
                    snapshot_boundary="archived_history_checkpoint"):
    if native_history is None:raise ValueError("native_history is required")
    from cs769.models.builders import layered
    from cs769.models.graphs.graph_memory_record_views import audit_record_view_render
    memory=layered(normalized_history,native_history,provider,native_context,
                   {"snapshot_boundary":snapshot_boundary},None)
    text=memory.render(memory.graph)
    check=audit_record_view_render(memory.graph,view="full",visible_observations=False,rendered_text=text)
    if not check["ok"]:raise ValueError("evidence graph render audit failed")
    return {"graph":memory.graph,"memory_text":text,"audits":{**memory.audits,"render":check}}
