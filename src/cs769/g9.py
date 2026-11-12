"""Public evaluated G9 profile; uses the same builder as the CLI."""
def build_g9_memory(normalized_history,native_history,*,provider="openai",native_context=None,
                    snapshot_boundary="archived_history_checkpoint"):
    if native_history is None:raise ValueError("native_history is required")
    from .builders import layered
    from .graphs.graph_memory_record_views import audit_record_view_render
    memory=layered(normalized_history,native_history,provider,native_context,
                   {"snapshot_boundary":snapshot_boundary},None)
    text=memory.render(memory.graph)
    check=audit_record_view_render(memory.graph,view="full",visible_observations=False,rendered_text=text)
    if not check["ok"]:raise ValueError("G9 render audit failed")
    return {"graph":memory.graph,"memory_text":text,"audits":{**memory.audits,"render":check}}
