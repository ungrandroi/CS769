"""Share repeated object-key schemas; keep every value and event occurrence.

The only selection signals are evidence graph payload ownership and identical ordered key
vectors. No tool names, task text, known answers, or continuation scores.
"""
from copy import deepcopy
from collections import defaultdict
from cs769.models.edits.record_edits import evidence, _digest, render as render_full
from cs769.models.edits.subtree_share import _index
from cs769.models.graphs.graph_memory_evidence import render_evidence_segments
from cs769.models.graphs.graph_memory_records import audit_record_graph

LEGEND='row(S,[values]) is an object with the ordered keys in schema S; values and occurrences stay distinct.\n'

def restore(graph):
    meta=graph['schema_sharing'];g=deepcopy(graph);del g['schema_sharing'];ns={n['id']:n for n in g['payload_layer']['nodes']}
    refs=meta['leaf_refs'];seen={}
    for node in ns.values():
        if 'key_text_ref' not in node:continue
        target=node.pop('key_text_ref')
        if refs.get(node['id'])!=target or target not in ns or 'text' not in ns[target] or 'key_text_ref' in ns[target]:raise ValueError('Invalid schema key alias')
        if 'text' in node or node['kind']!='fragment':raise ValueError('Invalid shared key leaf')
        node['text']=ns[target]['text'];seen[node['id']]=target
    if seen!=refs or _digest(g)!=meta['original_graph_sha256']:raise ValueError('Schema restore differs from source')
    if not audit_record_graph(g)['ok']:raise ValueError('Invalid restored evidence graph')
    ns,expand,tree=_index(g);objects=set();labels=set();expected={}
    for group in meta['groups']:
        if group['label'] in labels:raise ValueError('Duplicate schema label')
        labels.add(group['label']);canonical=group['objects'][0]
        canonical_keys=[ns[m]['key'] for m in ns[canonical]['members']]
        vector=[expand(k) for k in canonical_keys]
        for obj in group['objects']:
            if obj in objects or ns[obj]['kind']!='object':raise ValueError('Duplicate or invalid object')
            objects.add(obj);keys=[ns[m]['key'] for m in ns[obj]['members']]
            if [expand(k) for k in keys]!=vector:raise ValueError('Unequal schema keys/order')
            if obj==canonical:continue
            for key,first in zip(keys,canonical_keys):
                leaves=[i for i in tree(key) if 'text' in ns[i]];sources=[i for i in tree(first) if 'text' in ns[i]]
                if len(leaves)!=len(sources):raise ValueError('Unequal key trees')
                expected.update(zip(leaves,sources))
    if expected!=refs:raise ValueError('Key aliases not owned by declared schemas')
    return g

def share_schema(graph,count):
    if not audit_record_graph(graph)['ok']:raise ValueError('Invalid evidence graph')
    ns,expand,tree=_index(graph);events={n['id']:n for n in graph['evidence_view']['nodes']};buckets=defaultdict(list)
    for field in graph['payload_layer']['fields']:
        if events[field['event_id']]['category']!='tool_result' or field['parse_fallback'] is not None:continue
        for i in tree(field['root']):
            n=ns[i]
            if n['kind']!='object' or len(n['members'])<2:continue
            keys=tuple(expand(ns[m]['key']) for m in n['members'])
            buckets[keys].append(i)
    groups=[];refs={};out=deepcopy(graph);outns={n['id']:n for n in out['payload_layer']['nodes']}
    for keys,objects in buckets.items():
        if len(objects)<3:continue
        # Reject groups whose repeated-key savings cannot pay their schema label.
        kcount=count(','.join(keys));estimated=(len(objects)-1)*kcount-7*len(objects)-12
        if estimated<=0:continue
        group={'label':f'S{len(groups)}','objects':objects};groups.append(group)
        canonical_keys=[ns[m]['key'] for m in ns[objects[0]]['members']]
        for obj in objects[1:]:
            keys_here=[ns[m]['key'] for m in ns[obj]['members']]
            for key,first in zip(keys_here,canonical_keys):
                leaves=[i for i in tree(key) if 'text' in ns[i]];sources=[i for i in tree(first) if 'text' in ns[i]]
                if len(leaves)!=len(sources):raise ValueError('Unsupported key shape')
                for old,new in zip(leaves,sources):
                    if ns[old]['text']!=ns[new]['text']:raise ValueError('Unequal key lexeme')
                    refs[old]=new;outns[old].pop('text');outns[old]['key_text_ref']=new
    if not groups:raise ValueError('No profitable repeated object schema')
    out['schema_sharing']={'version':'g9-schema-share-v1','original_graph_sha256':_digest(graph),'groups':groups,'leaf_refs':refs}
    assert restore(out)==graph
    before=count(render_full(graph));after=count(render(out))
    if after>=before:raise ValueError('Schema overhead exceeds savings')
    return out,{'version':'g9-schema-share-v1','operation':'share_schema','action':{'groups':groups},
        'source_graph_sha256':_digest(graph),'edited_graph_sha256':_digest(out),'memory_tokens_before':before,
        'memory_tokens_after':after,'saved_tokens':before-after,'applied':True,'retained_evidence_exact':True,
        'full_original_evidence_preserved':True,'restored_graph_exact':True,'task_preservation_certified':False,
        'tool_names_or_task_text_used':False,'display_note':'Object punctuation becomes explicit schema/row notation; string content, value types and order remain exact.'}

def render(graph):
    if 'schema_sharing' not in graph:return render_full(graph)
    g=restore(graph);ns,expand,tree=_index(g);objects={o:x['label'] for x in graph['schema_sharing']['groups'] for o in x['objects']}
    defs=[]
    for group in graph['schema_sharing']['groups']:
        n=ns[group['objects'][0]];defs.append(group['label']+'=['+','.join(expand(ns[m]['key']) for m in n['members'])+']\n')
    def compact(i):
        n=ns[i]
        if i in objects:return 'row('+objects[i]+',['+','.join(compact(ns[m]['value']) for m in n['members'])+'])'
        return n['text'] if 'text' in n else ''.join(compact(c) for c in n['parts'])
    segments=render_evidence_segments(evidence(g));body=''.join(s['text'] for s in segments);full=render_full(g);assert full.startswith(body)
    fields={(f['event_id'],f['field']):f for f in g['payload_layer']['fields']};output=[]
    for s in segments:
        f=fields.get((s.get('node_id'),s.get('field')))
        if s['kind']=='evidence' and f:
            assert s['text']==expand(f['root']);output.append(compact(f['root']))
        else:output.append(s['text'])
    output[0]+=LEGEND+''.join(defs)
    return ''.join(output)+full[len(body):]
