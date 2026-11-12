"""Tool- and task-independent merging of equal payload subtrees in G9.

No values, events, occurrences, array positions, or relationships are deleted.
Only exact repeated subtrees share storage and model-facing references.
All alias ownership is validated by graph-only restoration to a frozen hash.
"""
from copy import deepcopy
from collections import defaultdict
from .g9_edit import evidence,render as render_full,_digest
from cs769.graphs.graph_memory_evidence import render_evidence_segments
from cs769.graphs.graph_memory_records import audit_record_graph

LEGEND='value_def(P,x) stores exact value x; value_ref(P) reuses it. Events and array positions remain distinct.\n'

def restore(graph):
    meta=graph['subtree_sharing'];g=deepcopy(graph);del g['subtree_sharing']
    byid={n['id']:n for n in g['payload_layer']['nodes']}
    declared={k:v for group in meta['groups'] for a in group['aliases'] for k,v in a['leaf_refs'].items()}
    seen={}
    for node in byid.values():
        if 'text_ref' not in node:continue
        target=node.pop('text_ref')
        if node['id'] not in declared or declared[node['id']]!=target:raise ValueError('Undeclared text alias')
        if target not in byid or 'text' not in byid[target] or 'text_ref' in byid[target]:raise ValueError('Dangling or chained alias')
        if node['kind'] not in ('fragment','opaque') or 'text' in node:raise ValueError('Invalid aliased leaf')
        node['text']=byid[target]['text'];seen[node['id']]=target
    if seen!=declared:raise ValueError('Missing alias leaf')
    if _digest(g)!=meta['original_graph_sha256']:raise ValueError('Graph restoration differs from source')
    if not audit_record_graph(g)['ok']:raise ValueError('Restored graph is invalid')
    nodes,expand,tree=_index(g);labels=set();owned=set()
    for group in meta['groups']:
        label=group['label'];canonical=group['canonical']
        if label in labels or not label.startswith('P') or not label[1:].isdigit():raise ValueError('Invalid shared-value label')
        labels.add(label)
        if canonical not in nodes or owned.intersection(tree(canonical)):raise ValueError('Overlapping canonical roots')
        owned.update(tree(canonical))
        for a in group['aliases']:
            root=a['root']
            if root not in nodes or owned.intersection(tree(root)):raise ValueError('Overlapping alias roots')
            if nodes[root]['kind']!=nodes[canonical]['kind'] or expand(root)!=expand(canonical):raise ValueError('Unequal referenced value')
            target_tree=tree(root);canonical_tree=tree(canonical)
            if len(target_tree)!=len(canonical_tree):raise ValueError('Unequal payload shape')
            expected={x:y for x,y in zip(target_tree,canonical_tree) if 'text' in nodes[x]}
            if a['leaf_refs']!=expected:raise ValueError('Alias ownership differs from subtree structure')
            owned.update(target_tree)
    return g

def _index(graph):
    nodes={n['id']:n for n in graph['payload_layer']['nodes']};memo={};owned={}
    def walk(i):
        if i not in memo:
            n=nodes[i]
            memo[i]=n['text'] if n['kind'] in ('fragment','opaque') else ''.join(walk(c) for c in n['parts'])
        return memo[i]
    def tree(i):
        if i not in owned:owned[i]=[i]+[v for c in nodes[i].get('parts',[]) for v in tree(c)]
        return owned[i]
    return nodes,walk,tree

def share_subtrees(graph,count):
    if not audit_record_graph(graph)['ok']:raise ValueError('Invalid source graph')
    nodes,expand,tree=_index(graph);events={n['id']:n for n in graph['evidence_view']['nodes']}
    buckets=defaultdict(list);order={k:i for i,k in enumerate(nodes)}
    for field in graph['payload_layer']['fields']:
        if events[field['event_id']]['category']!='tool_result' or field['parse_fallback'] is not None:continue
        for i in tree(field['root']):
            n=nodes[i]
            if n['kind'] not in ('object','array','scalar'):continue
            text=expand(i)
            if len(text)<100:continue
            if count(text)<40:continue
            buckets[(n['kind'],text)].append(i)
    proposals=[]
    for (kind,text),ids in buckets.items():
        ids=sorted(set(ids),key=order.get)
        if len(ids)<2:continue
        estimate=(len(ids)-1)*count(text)-12*len(ids)
        if estimate>0:proposals.append((estimate,ids))
    proposals.sort(key=lambda x:(-x[0],order[x[1][0]]))
    occupied=set();groups=[];out=deepcopy(graph);outnodes={n['id']:n for n in out['payload_layer']['nodes']}
    for _,ids in proposals:
        available=[i for i in ids if not occupied.intersection(tree(i))]
        if len(available)<2:continue
        canonical=available[0];base=tree(canonical);group={'label':f'P{len(groups)}','canonical':canonical,'aliases':[]}
        for root in available[1:]:
            target=tree(root)
            if len(target)!=len(base):continue
            # Equal literal values may have different source spans; retain every
            # original node's structural metadata and alias only literal leaves.
            leaf_refs={}
            for old,new in zip(target,base):
                a,b=nodes[old],nodes[new]
                if a['kind']!=b['kind']:break
                if 'text' in a:
                    if a['text']!=b.get('text'):break
                    leaf_refs[old]=new
            else:
                for old,new in leaf_refs.items():
                    outnodes[old].pop('text');outnodes[old]['text_ref']=new
                group['aliases'].append({'root':root,'leaf_refs':leaf_refs})
                occupied.update(target)
                continue
            continue
        if group['aliases']:
            occupied.update(base);groups.append(group)
    if not groups:raise ValueError('No eligible repeated payload subtree')
    out['subtree_sharing']={'version':'g9-subtree-share-v1','original_graph_sha256':_digest(graph),'groups':groups}
    assert restore(out)==graph
    text=render(out);before=count(render_full(graph));after=count(text)
    if after>=before:raise ValueError('Reference overhead exceeds sharing benefit')
    return out,{'version':'g9-subtree-share-v1','operation':'share_subtrees','action':{'groups':groups},
        'source_graph_sha256':_digest(graph),'edited_graph_sha256':_digest(out),
        'memory_tokens_before':before,'memory_tokens_after':after,'saved_tokens':before-after,
        'applied':True,'retained_evidence_exact':True,'full_original_evidence_preserved':True,
        'restored_graph_exact':True,'task_preservation_certified':False,'tool_names_or_task_text_used':False}

def render(graph):
    if 'subtree_sharing' not in graph:return render_full(graph)
    g=restore(graph);nodes,expand,tree=_index(g)
    canonical={x['canonical']:x['label'] for x in graph['subtree_sharing']['groups']}
    aliases={a['root']:x['label'] for x in graph['subtree_sharing']['groups'] for a in x['aliases']}
    def compact(i):
        if i in aliases:return 'value_ref('+aliases[i]+')'
        n=nodes[i];value=n['text'] if 'text' in n else ''.join(compact(c) for c in n['parts'])
        return 'value_def('+canonical[i]+','+value+')' if i in canonical else value
    fields={(f['event_id'],f['field']):f for f in g['payload_layer']['fields']}
    segments=render_evidence_segments(evidence(g));body=''.join(s['text'] for s in segments);full=render_full(g)
    assert full.startswith(body)
    parts=[]
    for s in segments:
        field=fields.get((s.get('node_id'),s.get('field')))
        if s['kind']=='evidence' and field:
            assert s['text']==expand(field['root'])
            parts.append(compact(field['root']))
        else:parts.append(s['text'])
    parts[0]+=LEGEND
    return ''.join(parts)+full[len(body):]
