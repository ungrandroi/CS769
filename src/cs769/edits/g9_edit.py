"""One real graph edit; source G9 remains immutable. No task/GT access.

Rebuild derived layers solely from the retained evidence view. Full-evidence
checks apply to the input, not to the intentionally lossy output.
"""
from copy import deepcopy
import json
from cs769.graphs.graph_memory_evidence import _digest, reconstruct_visible_evidence, audit_evidence_graph
from cs769.graphs.graph_memory_observed import strip_observed_graph, build_observed_graph
from cs769.graphs.graph_memory_payload import restore_observed_graph, build_payload_graph, _expand
from cs769.graphs.graph_memory_records import strip_record_graph, build_record_graph, audit_record_graph, plan_record_projection
from cs769.graphs.graph_memory_record_views import render_record_view_graph

# Delete ancillary fields only; never delete IDs, status/error flags, timestamps,
# units or selector fields. This is structural validity, NOT a safety guarantee.
PROJECT_FIELDS = {
    'post_tweet': {'tags', 'mentions'},
    'get_stock_info': {'volume', 'MA(5)', 'MA(20)'},
    'get_order_details': {'metadata'},
    'estimate_distance': {'intermediaryCities'},
    'startEngine': {'fuelLevel', 'batteryVoltage'},
    'book_flight': {'booking_history'},
}

def evidence(g):
    if not audit_record_graph(g)['ok']: raise ValueError('Invalid source G9')
    return strip_observed_graph(restore_observed_graph(strip_record_graph(g)))

def render(g):
    return render_record_view_graph(g, view='full', visible_observations=False)

def candidates(g, project_fields=None):
    project_fields=PROJECT_FIELDS if project_fields is None else project_fields
    e=evidence(g); records=[n for n in e['evidence_view']['nodes'] if n['category']!='episode']
    calls={n['id']:n for n in records if n['category']=='tool_call'}
    groups={}
    for n in calls.values(): groups.setdefault(n['call_group'],[]).append(n['id'])
    # Preserve most recent tool exchange/group. Earlier groups may be unsafe;
    # measured continuation outcomes, not this rule, determine task impact.
    last=next(reversed(groups),None)
    deletes=[{'kind':'delete','call_group':k,'event_ids':v+[n['id'] for n in records if n.get('result_of') in v]} for k,v in groups.items() if k!=last]
    payload=g['payload_layer']; ids={n['id']:n for n in payload['nodes']}; byevent={n['id']:n for n in records}
    projects=[]
    for f in payload['fields']:
        n=byevent[f['event_id']]
        if n['category']!='tool_result' or n.get('native_is_error'): continue
        call=calls[n['result_of']]; tool=call['fields'][0]['value']
        if tool not in project_fields or f['parse_fallback'] is not None: continue
        root=ids[f['root']]; obj=ids[root['value']] if root['kind']=='document' else root
        if obj['kind']!='object' or len(obj['members'])<2: continue
        for mid in obj['members']:
            key=json.loads(_expand(ids[mid]['key'],ids))
            if key in project_fields[tool]:
                projects.append({'kind':'project','event_id':n['id'],'field':f['field'],'member_id':mid,'tool':tool,'key':key})
    return deletes,projects

def _refresh(e):
    view=e['evidence_view'];records=[n for n in view['nodes'] if n['category']!='episode']
    mapping={n['id']:f'e{i}' for i,n in enumerate(records)};nodes=[];edges=[];seen=set();previous=None
    for i,n in enumerate(records):
        n['id']=mapping[n['id']];n['ordinal']=i
        if n['episode'] not in seen:
            nodes.append({'id':n['episode'],'category':'episode','turn':n['turn']});seen.add(n['episode'])
        nodes.append(n)
        if 'result_of' in n:
            n['result_of']=mapping[n['result_of']]
            edges.append({'from':n['id'],'relation':'result_of','to':n['result_of']})
        edges.append({'from':n['id'],'relation':'in_turn','to':n['episode']})
        if previous is not None:edges.append({'from':previous,'relation':'precedes','to':n['id']})
        previous=n['id']
    view.update(nodes=nodes,edges=edges,recorded_order=[n['id'] for n in records])
    e['evidence_audit']={'view_sha256':_digest(view),'visible_sha256':_digest(reconstruct_visible_evidence(e))}
    audit_evidence_graph(e)
    return build_record_graph(build_payload_graph(build_observed_graph(e,variant='observed-fields-v1')),variant='record-joins-v1'),mapping

def apply(g, action, token_count, *, project_fields=None):
    oldhash=_digest(g);e=evidence(g); original=deepcopy(e)
    ds,ps=candidates(g, project_fields)
    if action not in ds+ps: raise ValueError('Action not in declared legal space')
    removed=[];changed=[]
    if action['kind']=='delete':
        targets=set(action['event_ids']); removed=[deepcopy(n) for n in e['evidence_view']['nodes'] if n['id'] in targets]
        e['evidence_view']['nodes']=[n for n in e['evidence_view']['nodes'] if n['id'] not in targets]
    else:
        plan=plan_record_projection(g,removed_member_ids=[action['member_id']])
        # Use ownership-tree deletions and separator repairs; preserve literal
        # spelling/whitespace of every retained fragment.
        payload=g['payload_layer'];ids={n['id']:n for n in payload['nodes']};drop=set(plan['payload_plan']['removed_payload_node_ids'])
        f=next(f for f in payload['fields'] if f['event_id']==action['event_id'] and f['field']==action['field'])
        def visit(i):
            if i in drop:return ''
            n=ids[i]
            return n['text'] if n['kind'] in ('fragment','opaque') else ''.join(visit(c) for c in n['parts'])
        text=visit(f['root']);newval=json.loads(text) if f['source_kind']=='typed-source' else text
        n=next(n for n in e['evidence_view']['nodes'] if n['id']==action['event_id'])
        field=next(x for x in n['fields'] if x['field']==action['field']);before=deepcopy(field['value'])
        oldobj=json.loads(before) if isinstance(before,str) else before
        newobj=json.loads(newval) if isinstance(newval,str) else newval
        expected={k:v for k,v in oldobj.items() if k!=action['key']}
        if newobj!=expected: raise ValueError('Projection changed a retained value')
        field['value']=newval;field['value_type']=type(newval).__name__
        changed.append({'event_id':action['event_id'],'field':action['field'],'before':before,'after':newval})
    edited,mapping=_refresh(e);text=render(edited);source=render(g)
    saving=token_count(source)-token_count(text)
    if saving<=0:raise ValueError('Edit does not reduce rendered tokens')
    if _digest(g)!=oldhash:raise AssertionError('Input graph mutated')
    # Map each surviving evidence node to source and check exact retention except
    # the one declared payload. Never relabel this as full-history preservation.
    src={n['id']:n for n in original['evidence_view']['nodes'] if n['category']!='episode'}
    dst={n['id']:n for n in evidence(edited)['evidence_view']['nodes'] if n['category']!='episode'}
    for oldid,newid in mapping.items():
        want=deepcopy(src[oldid]);want['id']=newid;want['ordinal']=dst[newid]['ordinal']
        if 'result_of' in want:want['result_of']=mapping[want['result_of']]
        if action['kind']=='project' and oldid==action['event_id']:
            for f in want['fields']:
                if f['field']==action['field']:f['value']=changed[0]['after'];f['value_type']=type(f['value']).__name__
        if want!=dst[newid]:raise AssertionError('Undeclared evidence change')
    return edited,{'version':'g9-edit-v1','action':action,'source_graph_sha256':oldhash,'edited_graph_sha256':_digest(edited),'removed_records':removed,'changed_fields':changed,'old_to_new_event_ids':mapping,'memory_tokens_before':token_count(source),'memory_tokens_after':token_count(text),'saved_tokens':saving,'applied':True,'retained_evidence_exact':True,'full_original_evidence_preserved':False,'task_preservation_certified':False}

def choose(g,kind,count):
    # Fixed, task-blind rule: largest saving, then stable action JSON. No eval.
    options=[]
    for a in candidates(g)[0 if kind=='delete' else 1]:
        try:edited,audit=apply(g,a,count)
        except ValueError:continue
        options.append((edited,audit))
    if not options:raise ValueError('No eligible '+kind+' action')
    return sorted(options,key=lambda x:(-x[1]['saved_tokens'],json.dumps(x[1]['action'],sort_keys=True)))[0]
