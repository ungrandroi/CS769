"""Shared graph construction. Builders return data and a graph-only renderer."""
from copy import deepcopy
from dataclasses import dataclass,field
from .history import dumps
from .registry import register_builder

@dataclass
class Memory:
    graph: dict|None
    render: object
    audits: dict = field(default_factory=dict)
    messages: list|None = None

def options(value, allowed):
    unknown=set(value)-set(allowed)
    if unknown:raise ValueError('Unknown module options: '+', '.join(sorted(unknown)))

def identity(history,native,provider,context,opt,count):
    options(opt,[])
    return Memory(None,lambda g:'')

def native(history,native,provider,context,opt,count):
    from .graphs.graph_memory_native import build_native_graph,render_native_index
    from .graphs.graph_memory_readable import render_readable
    options(opt,['format','snapshot_boundary'])
    g=build_native_graph(history,native,provider=provider,native_context=context,snapshot_boundary=opt.get('snapshot_boundary','archived_history_checkpoint'))
    fmt=opt.get('format','index')
    if fmt not in ('index','readable'):raise ValueError('Unknown native format')
    return Memory(g,render_native_index if fmt=='index' else render_readable)

def evidence(history,native,provider,context,opt,count):
    from .graphs.graph_memory_evidence import build_evidence_graph,audit_evidence_graph,inference_graph,render_evidence_graph
    options(opt,['episodic_only','include_entity_origin','layout','snapshot_boundary'])
    archive=build_evidence_graph(history,native,provider=provider,native_context=context,episodic_only=opt.get('episodic_only',True),include_entity_origin=opt.get('include_entity_origin',False),snapshot_boundary=opt.get('snapshot_boundary','archived_history_checkpoint'))
    audit=audit_evidence_graph(archive,normalized_history=history,native_history=native)
    if not audit['integrity_ok']:raise ValueError('Evidence integrity failed')
    return Memory(inference_graph(archive),lambda g:render_evidence_graph(g,layout=opt.get('layout','chronological-first')),{'evidence':audit})

def layered(history,native,provider,context,opt,count):
    options(opt,['layer','variant','render','view','visible_observations','layout','snapshot_boundary','role_mode','seeds','query_arm','query_branch'])
    m=evidence(history,native,provider,context,{k:v for k,v in opt.items() if k=='snapshot_boundary'},count)
    layer=opt.get('layer','record');variant=opt.get('variant')
    if layer=='anchors':
        from .graphs.graph_memory_structured import build_structured_graph,render_structured_graph
        m.graph=build_structured_graph(m.graph,variant=variant or 'anchors-v1');m.render=render_structured_graph
    else:
        from .graphs.graph_memory_observed import build_observed_graph,render_observed_graph
        m.graph=build_observed_graph(m.graph,variant=(variant or 'observed-fields-v1') if layer=='observed' else 'observed-fields-v1')
        m.render=render_observed_graph
        if layer in ('payload','record'):
            from .graphs.graph_memory_payload import build_payload_graph,render_payload_graph
            m.graph=build_payload_graph(m.graph);m.render=lambda g:render_payload_graph(g,layout=opt.get('layout','inline-members-v1'))
        if layer=='record':
            from .graphs.graph_memory_records import build_record_graph,audit_record_graph,render_record_graph
            m.graph=build_record_graph(m.graph,variant=variant or 'record-joins-v1')
            check=audit_record_graph(m.graph)
            if not check['ok']:raise ValueError(str(check['errors']))
            m.audits['record']=check;fmt=opt.get('render','view')
            if fmt=='view':
                from .graphs.graph_memory_record_views import render_record_view_graph
                m.render=lambda g:render_record_view_graph(g,view=opt.get('view','full'),visible_observations=opt.get('visible_observations',False))
            elif fmt=='inline':m.render=render_record_graph
            elif fmt=='external':
                from .graphs.graph_memory_record_render import render_external_record_graph
                m.render=render_external_record_graph
            elif fmt=='visibility':
                from .graphs.graph_memory_record_visibility import render_record_visibility_graph
                m.render=lambda g:render_record_visibility_graph(g,visible_observations=opt.get('visible_observations',False))
            elif fmt=='signature':
                from .graphs.graph_memory_signature import render_signature_graph
                m.render=lambda g:render_signature_graph(g,layout='call-signatures-v1')
            elif fmt=='encoding':
                from .graphs.graph_memory_encoding import render_encoding_graph
                m.render=lambda g:render_encoding_graph(g,layout=opt.get('layout','event-blocks-v1'))
            elif fmt=='lexical':
                from .graphs.graph_memory_lexical import build_lexical_graph,render_lexical_graph
                m.graph=build_lexical_graph(m.graph)
                m.render=lambda g:render_lexical_graph(g,layout=opt.get('layout','external-record-evidence-v1'))
            elif fmt=='content_store':
                from .graphs.graph_memory_content_store import render_content_store_graph
                m.render=render_content_store_graph
            elif fmt=='query_layout':
                from .graphs import query_layout as q,graph_memory_evidence as e,graph_memory_observed as o,graph_memory_payload as p,graph_memory_records as r,graph_memory_record_views as v
                arm=opt.get('query_arm','C');branch=opt.get('query_branch','whole_episode');seeds=opt.get('seeds',[])
                if arm not in ('C','S','G'):raise ValueError('Unknown query layout arm')
                if not isinstance(seeds,list) or len(seeds)>1:raise ValueError('Expected zero or one explicit seed exchange')
                def render(g):
                    prepared=q.prepare(g,(e,o,p,r,v));info,orders=q.variants(prepared,branch,seeds)
                    if not info['valid'] or info['fallback']:raise ValueError('Invalid query seed or unsafe partition')
                    segments=q.segment_list(prepared,branch,orders[arm]);audit=q.audit_layout(prepared,branch,orders[arm],segments)
                    if not audit['all_checks_passed']:raise ValueError('Query layout evidence audit failed')
                    return ''.join(s['text'] for s in segments)
                m.render=render
            elif fmt=='role_partition':
                from .graphs.graph_memory_role_partition import compile_graph_partition
                m.messages=compile_graph_partition(m.graph,role_mode=opt.get('role_mode','historical-user'))
                m.render=lambda g:''.join(x['content'] for x in compile_graph_partition(g,role_mode=opt.get('role_mode','historical-user')))
            else:raise ValueError('Unknown record renderer')
        elif layer not in ('observed','payload'):raise ValueError('Unknown graph layer')
    return m

def semantic(history,native,provider,context,opt,count):
    from .graphs import optimized_graph,lossless_event,lossless_state,mixed_graph
    options(opt,['kind','semantics','codec','explanation'])
    kind=opt.get('kind','event');codec=opt.get('codec','tables-v1');explanation=opt.get('explanation','minimal')
    if kind not in ('event','state','event_dedup'):raise ValueError('Unknown semantic graph kind')
    method={'event':'v2-compact','state':'v1-compact','event_dedup':'v2-dedup'}[kind]
    mode=opt.get('semantics','filesystem')
    if mode not in ('filesystem','mixed'):raise ValueError('Unknown semantic scope')
    if codec=='legacy':
        from .graphs.state_transition_graph import GraphMemory
        from .graphs.event_graph import GraphMemoryV2
        from .graphs.graph_memory_serialization_target import encode_compact
        from .graphs.event_graph_dedup import encode
        if mode!='filesystem':raise ValueError('Legacy compact uses filesystem semantics')
        from .graphs.graph_memory_replace import GraphMemoryReplacement,GraphMemoryV2Replacement
        builder=GraphMemoryReplacement() if kind=='state' else GraphMemoryV2Replacement()
        builder.build(history)
        g=__import__('json').loads(builder.render().split('\n',2)[2])
        return Memory(g,(lambda x:encode(x,count)[0]) if kind=='event_dedup' else (lambda x:encode_compact(x,count)))
    _,meta=(mixed_graph if mode=='mixed' else optimized_graph).build_memory(history,method,explanation,count)
    original=meta['graph']
    if codec=='original':encoded=original;restored=deepcopy(encoded)
    elif kind=='state':encoded=lossless_state.encode(original,candidate=codec);restored=lossless_state.decode(encoded)
    else:encoded=lossless_event.encode(original,variant=codec);restored=lossless_event.decode(encoded)
    if restored!=original:raise ValueError('Semantic codec roundtrip failed')
    prefix=meta['instruction']
    return Memory(encoded,lambda g:(prefix+'\n' if prefix else '')+dumps(g),{'history_exact':True,'codec_roundtrip':True,'semantics':mode})

for name,fn in [('identity',identity),('native_index',native),('readable',native),('evidence',evidence),('g9',layered),('layered',layered),('semantic',semantic)]:register_builder(name,fn)
