"""Offline feasibility of sharing exactly equal result text. No API or eval.

The output is a proposed model-facing serialization and an action manifest,
not a completed shared-payload graph implementation or a task-safety claim.
"""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
from cs769.models.graphs.graph_memory_evidence import render_evidence_segments
from cs769.models.graphs.graph_memory_record_views import render_record_view_graph
from cs769.models.edits.record_edits import evidence

LEGEND="output_ref=E.output reuses E's exact output; the events remain distinct.\n"

def groups_in_history(history):
    calls={m['call_id']:m for m in history if m.get('type')=='function_call'}
    groups=defaultdict(list)
    for i,m in enumerate(history):
        if m.get('type')=='function_call_output':
            c=calls[m['call_id']]
            # Sharing output bytes does not equate the arguments/entities/events.
            key=json.dumps([c['name'],type(m['output']).__name__,m['output']],ensure_ascii=False,sort_keys=True)
            groups[key].append(i)
    return [v for v in groups.values() if len(v)>1]

def graph_groups(g):
    e=evidence(g);nodes=e['evidence_view']['nodes']
    calls={n['id']:n for n in nodes if n['category']=='tool_call'};groups=defaultdict(list)
    for n in nodes:
        if n['category']!='tool_result':continue
        tool=next(f['value'] for f in calls[n['result_of']]['fields'] if f['field']=='name')
        f=next(f for f in n['fields'] if f['field']=='output')
        key=json.dumps([tool,f,n.get('native_is_error')],ensure_ascii=False,sort_keys=True)
        groups[key].append(n['id'])
    return e,[(json.loads(k)[0],v) for k,v in groups.items() if len(v)>1]

def preview(g,ids):
    e,groups=graph_groups(g)
    if ids not in [v for _,v in groups]:raise ValueError('Not an exact same-tool output group')
    segments=render_evidence_segments(e)
    full=render_record_view_graph(g,view='full',visible_observations=False)
    body=''.join(s['text'] for s in segments);assert full.startswith(body)
    targets=set(ids[1:]);first=ids[0];edits=[]
    # Replace typed field spans, never search source text for apparent markers.
    for i,s in enumerate(segments):
        if s['kind']=='evidence' and s.get('node_id') in targets and s.get('field')=='output':
            assert segments[i-1]['kind']=='label' and segments[i+1]['kind']=='label'
            edits.append((i-1,i+2,s['node_id']))
    output=[];cursor=0;blocks=[]
    for start,end,event in edits:
        output.extend(segments[cursor:start])
        output.append({'kind':'output_reference','event_id':event,'target_event':first,
                       'text':f'output_ref={first}.output\n'})
        blocks.append({'event_id':event,'target_event':first,'original_segments':segments[start:end]})
        cursor=end
    output.extend(segments[cursor:]);output=deepcopy(output)
    output[0]['text']+=LEGEND
    # Prove this encoding can expand to the unchanged evidence graph rendered input. This
    # check uses only the original first occurrence, not a copy per reference.
    first_i=next(i for i,s in enumerate(segments) if s['kind']=='evidence' and s.get('node_id')==first and s.get('field')=='output')
    first_text=segments[first_i]['text'];expanded=[]
    for s in output:
        if s['kind']=='output_reference':
            record=next(b for b in blocks if b['event_id']==s['event_id'])
            original=record['original_segments']
            assert original[1]['text']==first_text
            expanded.extend([original[0]['text'],first_text,original[2]['text']])
        elif s is output[0]:expanded.append(s['text'][:-len(LEGEND)])
        else:expanded.append(s['text'])
    assert ''.join(expanded)==body
    return ''.join(s['text'] for s in output)+full[len(body):],{
        'canonical_event':first,'referencing_events':ids[1:],
        'all_original_events_retained':True,'all_original_order_and_call_edges_retained':True,
        'equal_payload_not_equal_entity_claim':True,'render_expands_exactly_to_full_g9':True,
        'shared_payload_graph_implementation_complete':False}
