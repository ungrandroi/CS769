"""Exact payload-node sharing; event identities and all G9 relations survive.

The shared graph owns one copy of each selected output's literal payload.
Alias nodes preserve existing paths/owners; neither native history nor an
archive is accepted by restore/render. Existing G9 builders are unchanged.
"""
from copy import deepcopy
from collections import defaultdict
from cs769.graphs.graph_memory_evidence import _digest
from cs769.graphs.graph_memory_records import audit_record_graph
from .inspect_merge import graph_groups,preview

VERSION='g9-shared-output-v1'

def _owned(root,nodes):
    found=[]
    def visit(i):
        found.append(i)
        for child in nodes[i].get('parts',[]):visit(child)
    visit(root)
    if len(set(found))!=len(found):raise ValueError('Source payload is not a tree')
    return found

def _translate(value,mapping,key=None):
    # Original text is opaque, even if it looks like an internal payload ID.
    if key=='text':return value
    if isinstance(value,str):return mapping.get(value,value)
    if isinstance(value,list):return [_translate(x,mapping) for x in value]
    if isinstance(value,dict):return {k:_translate(v,mapping,k) for k,v in value.items()}
    return value

def restore(shared):
    meta=shared['sharing_layer']
    if meta['version']!=VERSION:raise ValueError('Unknown sharing version')
    out=deepcopy(shared);del out['sharing_layer']
    nodes={n['id']:n for n in out['payload_layer']['nodes']};aliases=defaultdict(list)
    for n in nodes.values():
        if n['kind']=='shared_payload_ref':
            if set(n)!={'id','kind','target','alias_group'}:raise ValueError('Malformed alias')
            if n['target'] not in nodes or nodes[n['target']]['kind']=='shared_payload_ref':
                raise ValueError('Dangling or chained alias')
            aliases[n['alias_group']].append(n)
    declared={g['alias_group'] for g in meta['aliases']}
    if declared!=set(aliases):raise ValueError('Alias ownership differs')
    replacements={}
    for group,refs in aliases.items():
        inverse={r['target']:r['id'] for r in refs}
        if len(inverse)!=len(refs):raise ValueError('Non-bijective alias tree')
        for r in refs:replacements[r['id']]=_translate(nodes[r['target']],inverse)
    out['payload_layer']['nodes']=[replacements.get(n['id'],n) for n in out['payload_layer']['nodes']]
    if _digest(out)!=meta['original_graph_sha256']:raise ValueError('Restored graph differs from original')
    if not audit_record_graph(out)['ok']:raise ValueError('Restored G9 failed integrity')
    return out

def merge(g,event_ids):
    if not audit_record_graph(g)['ok']:raise ValueError('Invalid original G9')
    _,groups=graph_groups(g)
    if event_ids not in [ids for _,ids in groups]:raise ValueError('Outputs are not exactly equal')
    out=deepcopy(g);nodes={n['id']:n for n in g['payload_layer']['nodes']}
    fields={(f['event_id'],f['field']):f for f in g['payload_layer']['fields']}
    canonical=fields[(event_ids[0],'output')]
    source_ids=_owned(canonical['root'],nodes);replacement={};aliases=[]
    for i,event in enumerate(event_ids[1:]):
        field=fields[(event,'output')];target_ids=_owned(field['root'],nodes)
        if len(source_ids)!=len(target_ids):raise ValueError('Payload shapes differ')
        mapping=dict(zip(target_ids,source_ids));group=f'a{i}'
        for old,new in mapping.items():
            if _translate(nodes[old],mapping)!=nodes[new]:raise ValueError('Payload structure or literal text differs')
            replacement[old]={'id':old,'kind':'shared_payload_ref','target':new,'alias_group':group}
        aliases.append({'alias_group':group,'event_id':event,'field':'output',
                        'canonical_event':event_ids[0],'canonical_field':'output'})
    out['payload_layer']['nodes']=[replacement.get(n['id'],n) for n in out['payload_layer']['nodes']]
    out['sharing_layer']={'version':VERSION,'original_graph_sha256':_digest(g),
                          'event_ids':event_ids,'aliases':aliases}
    if restore(out)!=g:raise AssertionError('Merge was lossy')
    return out

def render(shared):
    # Expansion is an internal audit/rendering operation. Only the final
    # reference-bearing text is handed to the model, never expanded/native text.
    g=restore(shared)
    return preview(g,shared['sharing_layer']['event_ids'])[0]
