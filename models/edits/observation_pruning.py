"""Delete one owned text subtree of an older observation, with explicit guards.
No task IDs, tool-name allowlist, future turns, or evaluator access.
Missing edges are not a correctness certificate. Numeric/status *fields* survive;
opaque prose may contain numeric wording and this is recorded in the edit audit.
"""
from copy import deepcopy
import json,re
from cs769.models.edits.record_edits import evidence, _refresh, _digest, render
from cs769.models.graphs.graph_memory_payload import _expand
from cs769.models.graphs.graph_memory_records import plan_record_projection, audit_record_graph

VERSION='g9-observation-pruning-v1'
PROTECTED_KEY=re.compile(r'(^id$|_id$|identifier|status|error|success|failure|token|password|secret|^key$|^path$|^name$|^content[s]?$|^text$|^body$|^message$)',re.I)

def _walk(nodes,root):
    yield root
    for child in nodes[root].get('parts',[]):yield from _walk(nodes,child)

def _strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for v in value.values():yield from _strings(v)
    elif isinstance(value,list):
        for v in value:yield from _strings(v)

def _pure_long_text(value):
    if isinstance(value,str):return len(value)>=80 and not re.fullmatch(r'[\d\W]+',value)
    if isinstance(value,dict):return bool(value) and all(not PROTECTED_KEY.search(k) and _pure_long_text(v) for k,v in value.items())
    if isinstance(value,list):return bool(value) and all(_pure_long_text(v) for v in value)
    return False

def _words(text):return set(re.findall(r'[a-z]{4,}',re.sub(r'([a-z])([A-Z])',r'\1 \2',text).lower()))

def candidates(graph,current,*,min_saved_tokens=50,count=len):
    if type(min_saved_tokens)is not int or min_saved_tokens<1:raise ValueError('Invalid savings threshold')
    ev=evidence(graph)['evidence_view']['nodes'];events={n['id']:n for n in ev if n['category']!='episode'}
    calls=[n for n in ev if n['category']=='tool_call'];last_group=calls[-1]['call_group'] if calls else None
    nodes={n['id']:n for n in graph['payload_layer']['nodes']}
    parents={c:n['id'] for n in nodes.values() for c in n.get('parts',[])}
    protected={n['payload_node'] for n in graph['record_layer']['nodes'] if n['category']=='identifier_occurrence'}
    protected.update(b['target'] for b in graph['payload_layer']['source_bindings'])
    query=_words(json.dumps(current,ensure_ascii=False));found=[];rejected={}
    def skip(reason):rejected[reason]=rejected.get(reason,0)+1
    for field in graph['payload_layer']['fields']:
        event=events[field['event_id']]
        if event['category']!='tool_result':continue
        call=events[event['result_of']]
        if call['call_group']==last_group or event.get('native_is_error') or field['parse_fallback'] is not None:continue
        try:whole=json.loads(_expand(field['root'],nodes))
        except ValueError:continue
        if not isinstance(whole,(dict,list)) or isinstance(whole,dict) and any(whole.get(k) for k in ('error','is_error')):continue
        # Explicit value reuse after this result is protected, including copies
        # in assistant text, arguments and current visible user messages.
        later=[]
        for n in ev:
            if n.get('ordinal',-1)>event['ordinal'] and n['category'] not in ('tool_result','episode'):
                later.extend(v for f in n.get('fields',[]) for v in _strings(f['value']))
        later.extend(_strings(current))
        for mid in _walk(nodes,field['root']):
            n=nodes[mid]
            if n['kind']!='member':continue
            parent=nodes[parents[mid]]
            if len(parent['members'])<2:skip('sole_member');continue
            key=json.loads(_expand(n['key'],nodes));raw=_expand(n['value'],nodes)
            try:value=json.loads(raw)
            except ValueError:continue
            if PROTECTED_KEY.search(key) or query.intersection(_words(key)):skip('protected_or_requested_field');continue
            if not _pure_long_text(value):skip('numeric_status_or_short_value');continue
            owned=set(_walk(nodes,mid))
            if owned.intersection(protected):skip('supported_identifier_or_observation');continue
            strings=list(_strings(value))
            if any(v in text or any(len(s.strip())>=30 and s.strip() in text for s in re.split(r'(?<=[.!?])\s+',v)) for v in strings for text in later):skip('explicit_later_reuse');continue
            if count(raw)<min_saved_tokens:skip('too_small');continue
            found.append({'kind':'prune_observation','event_id':event['id'],'field':field['field'],'member_id':mid,'key':key,'ordinal':event['ordinal'],'estimated_value_tokens':count(raw),'source_graph_sha256':_digest(graph),'removed_prose_contains_digits':any(c.isdigit() for c in raw)})
    return found,rejected

def apply(graph,action,count):
    if action['source_graph_sha256']!=_digest(graph):raise ValueError('Stale action')
    plan=plan_record_projection(graph,removed_member_ids=[action['member_id']])
    pp=plan['payload_plan']
    if pp['required_removed_semantic_node_ids'] or pp['required_removed_semantic_edge_ids']:raise ValueError('Edit removes supported semantics')
    if plan.get('required_removed_record_node_ids') or plan.get('required_removed_record_edge_ids'):raise ValueError('Edit removes identifier relationships')
    nodes={n['id']:n for n in graph['payload_layer']['nodes']};drop=set(pp['removed_payload_node_ids'])
    f=next(f for f in graph['payload_layer']['fields'] if f['event_id']==action['event_id'] and f['field']==action['field'])
    def visit(i):
        if i in drop:return ''
        n=nodes[i]
        return n['text'] if n['kind'] in ('fragment','opaque') else ''.join(visit(c) for c in n['parts'])
    text=visit(f['root']);json.loads(text)
    newvalue=json.loads(text) if f['source_kind']=='typed-source' else text
    before=evidence(graph);after=deepcopy(before)
    target=next(n for n in after['evidence_view']['nodes'] if n['id']==action['event_id'])
    changed=next(x for x in target['fields'] if x['field']==action['field']);changed['value']=newvalue;changed['value_type']=type(newvalue).__name__
    edited,mapping=_refresh(after)
    if mapping!={k:k for k in mapping}:raise AssertionError('Unexpected event renumbering')
    expected=deepcopy(before)
    target=next(n for n in expected['evidence_view']['nodes'] if n['id']==action['event_id'])
    changed=next(x for x in target['fields'] if x['field']==action['field']);changed['value']=newvalue;changed['value_type']=type(newvalue).__name__
    if expected['evidence_view']!=evidence(edited)['evidence_view']:raise AssertionError('Undeclared evidence change')
    if not audit_record_graph(edited)['ok']:raise AssertionError('Invalid edited graph')
    saved=count(render(graph))-count(render(edited))
    if saved<=0:raise ValueError('No positive rendered saving')
    return edited,{'version':VERSION,'action':action,'source_graph_sha256':_digest(graph),'edited_graph_sha256':_digest(edited),'saved_tokens':saved,'memory_tokens_before':count(render(graph)),'memory_tokens_after':count(render(edited)),'retained_evidence_exact':True,'all_events_retained':True,'full_original_evidence_preserved':False,'task_preservation_certified':False,'removed_payload_nodes':pp['removed_payload_node_ids'],'removed_prose_contains_digits':action['removed_prose_contains_digits'],'numeric_and_status_fields_protected':True}

def prune(graph,count,current,*,min_saved_tokens=50):
    actions,_=candidates(graph,current,min_saved_tokens=min_saved_tokens,count=count)
    for action in sorted(actions,key=lambda x:(-x['estimated_value_tokens'],x['ordinal'],x['member_id'])):
        try:edited,audit=apply(graph,action,count)
        except ValueError:continue
        if audit['saved_tokens']>=min_saved_tokens:return edited,audit
    raise ValueError('No eligible protected observation subtree')
