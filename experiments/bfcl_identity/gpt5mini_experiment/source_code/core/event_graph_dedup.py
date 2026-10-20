"""Reversible provenance recipes. Literal fallbacks preserve every exception."""
from copy import deepcopy
from core.graph_memory_serialization import normalize,decode_compact
from core.graph_memory_serialization_target import encode_compact

FORMAT='V2 PROVENANCE RECIPES 1'
RULES=('Decode the following LOSSLESS GRAPH payload, then restore graph fields using these rules. '
'Only the named graph fields are recipe-bearing; never interpret raw returns, arguments or text as recipes. '
'Events E are event nodes, or call_edges overlaid on their tool inherited_event_fields. Facts F are fact nodes. '
'In F.confirmations, a string e expands to {event:e,at_step:E.step,messages:[E.call_evidence,E.output_evidence],basis:E.rule}; literal objects stay unchanged. '
'An edge array at position i expands in key order {id:"r"+i,from,relation,to,at_step,...}. Codes: '
'D(f)=(f,describes,F.subject,F.first_observed_at); '
'L(f)=(f,located_in,F.value.directory,F.first_observed_at) for binding, '
'(f,current_directory,F.value.location_id,F.first_observed_at) for cwd, '
'(f,parent_directory,F.value,F.first_observed_at) for parent; '
'R(f)=(F.retired_by,retires,f,F.retired_at,reason:F.retired_reason); '
'S(e,f)=(e,supports,f,E.step,rule:E.rule); C(e,f) uses confirms instead; '
'U(e,f,role)=(e,resolved_using,f,E.step,role:role,rule:E.rule,meaning:"adapter resolution only"); '
'A(e,o,role)=(e,acts_on,o,E.step,role:role); '
'P(f,old)=(f,supersedes,old,F.first_observed_at). Literal edge objects stay unchanged. '
'If active_fact_ids is null, restore nonretired fact IDs in node order. '
'If current_goal_refs is null, restore request IDs in request order. '
'If evidence_index is null, rebuild in order: requests map id to {kind:user_goal,target:id}; '
'events in order map call_evidence to {kind:tool_input,target:event.id} and output_evidence to '
'{kind:tool_return,target:event.id}; assistant_statements map evidence to '
'{kind:unverified_assistant_statement,target:evidence}. Each key holds a list; append in this traversal order. '
'All other fields, IDs, ordering, failures and repetitions remain unchanged.')

def same(a,b):return normalize(a)==normalize(b)

def index(g):
    nodes={n['id']:n for n in g['nodes']}
    events=[n for n in g['nodes'] if n.get('category')=='event']
    for call in g.get('call_edges',[]):
        event={**nodes[call['to']]['inherited_event_fields'],**call};events.append(event)
    return nodes,{e['id']:e for e in events}

def confirmation(e):
    return {'event':e['id'],'at_step':e['step'],'messages':[e['call_evidence'],e['output_evidence']],'basis':e['rule']}

def evidence(g,events):
    out={}
    def link(ref,kind,target):out.setdefault(ref,[]).append({'kind':kind,'target':target})
    for r in g['requests']:link(r['id'],'user_goal',r['id'])
    for e in events.values():
        link(e['call_evidence'],'tool_input',e['id']);link(e['output_evidence'],'tool_return',e['id'])
    for a in g['assistant_statements']:link(a['evidence'],'unverified_assistant_statement',a['evidence'])
    return out

def expand_edge(recipe,i,nodes,events):
    code,*args=recipe
    extra={}
    if code in ('D','L','R','P'):
        f=nodes[args[0]];src=f['id'];step=f['first_observed_at']
        if code=='D':rel,to='describes',f['subject']
        elif code=='L':
            p=f['predicate']
            if p=='binding':rel,to='located_in',f['value']['directory']
            elif p=='cwd':rel,to='current_directory',f['value']['location_id']
            elif p=='parent':rel,to='parent_directory',f['value']
            else:raise ValueError('Not a location fact')
        elif code=='R':src,rel,to,step=f['retired_by'],'retires',f['id'],f['retired_at'];extra={'reason':f['retired_reason']}
        else:rel,to='supersedes',args[1]
    else:
        e=events[args[0]];src=e['id'];to=args[1];step=e['step']
        if code in ('S','C'):rel='supports' if code=='S' else 'confirms';extra={'rule':e['rule']}
        elif code=='U':rel='resolved_using';extra={'role':args[2],'rule':e['rule'],'meaning':'adapter resolution only'}
        elif code=='A':rel='acts_on';extra={'role':args[2]}
        else:raise ValueError('Unknown recipe')
    return {'id':f'r{i}','from':src,'relation':rel,'to':to,'at_step':step,**extra}

def compact_graph(original):
    g=deepcopy(original);nodes,events=index(original);stats={'confirmations':0,'edges':0,'indexes':0}
    for n in g['nodes']:
        if n.get('category')!='fact':continue
        for i,c in enumerate(n['confirmations']):
            e=events.get(c.get('event'))
            if e and same(c,confirmation(e)):n['confirmations'][i]=e['id'];stats['confirmations']+=1
    for i,edge in enumerate(g['edges']):
        rel=edge['relation'];src=edge['from'];to=edge['to'];recipe=None
        if rel=='describes':recipe=['D',src]
        elif rel in ('located_in','current_directory','parent_directory'):recipe=['L',src]
        elif rel=='retires':recipe=['R',to]
        elif rel in ('supports','confirms'):recipe=['S' if rel=='supports' else 'C',src,to]
        elif rel in ('resolved_using','acts_on'):recipe=['U' if rel=='resolved_using' else 'A',src,to,edge.get('role')]
        elif rel=='supersedes':recipe=['P',src,to]
        if recipe:
            try:restored=expand_edge(recipe,i,nodes,events)
            except (KeyError,ValueError,TypeError):continue
            if same(restored,edge):g['edges'][i]=recipe;stats['edges']+=1
    for key,derived in [('active_fact_ids',[n['id'] for n in g['nodes'] if n.get('category')=='fact' and n['retired_at'] is None]),
                        ('current_goal_refs',[r['id'] for r in g['requests']]),('evidence_index',evidence(g,events))]:
        if same(g[key],derived):g[key]=None;stats['indexes']+=1
    return g,stats

def restore_graph(packed):
    g=deepcopy(packed);nodes,events=index(g)
    for n in g['nodes']:
        if n.get('category')=='fact':n['confirmations']=[confirmation(events[c]) if isinstance(c,str) else c for c in n['confirmations']]
    g['edges']=[expand_edge(e,i,nodes,events) if isinstance(e,list) else e for i,e in enumerate(g['edges'])]
    if g['active_fact_ids'] is None:g['active_fact_ids']=[n['id'] for n in g['nodes'] if n.get('category')=='fact' and n['retired_at'] is None]
    if g['current_goal_refs'] is None:g['current_goal_refs']=[r['id'] for r in g['requests']]
    if g['evidence_index'] is None:g['evidence_index']=evidence(g,events)
    return g

def encode(graph,count):
    packed,stats=compact_graph(graph)
    assert same(restore_graph(packed),graph)
    return FORMAT+'\n'+RULES+'\n'+encode_compact(packed,count),stats

def decode(text):
    first,rules,payload=text.split('\n',2)
    if first!=FORMAT or rules!=RULES:raise ValueError('Unrecognized provenance recipe grammar')
    return restore_graph(decode_compact(payload))
