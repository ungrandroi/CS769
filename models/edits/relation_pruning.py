"""Relation-guided, intentionally lossy evidence graph edits.

No task identifiers, future requests, answers, evaluator or network access.
Relations are observational witnesses, not proofs of task safety or causality.
Read contracts below are reviewed public BFCL tool semantics, not task rules.
"""
from copy import deepcopy
import json,re
from cs769.models.edits.record_edits import evidence as _evidence, _refresh, _digest, render as full_render
from cs769.models.graphs.graph_memory_records import audit_record_graph

VERSION='g9-relation-pruning-v1'
READ_SCOPES={
 'ls':'cwd','cat':'cwd','head':'cwd','tail':'cwd','wc':'cwd','grep':'cwd','find':'cwd','diff':'cwd','pwd':'cwd',
 'displayCarStatus':'vehicle','get_current_speed':'vehicle','check_tire_pressure':'vehicle',
 'get_stock_info':'stock','get_order_details':'account','get_account_info':'account','get_watchlist':'account',
 'get_flight_cost':'flight',
}
HISTORY_QUERY=re.compile(r'\b(previous|previously|prior|earlier|before|historical|history|original|compare|comparison|difference|trend|average|again)\b',re.I)
ID_KEY=re.compile(r'(^id$|_id$|identifier|token|password|secret)',re.I)
def base_graph(g):
    out=deepcopy(g);out.pop('relation_pruning',None);return out
def evidence(g):return _evidence(base_graph(g))
def load(v):
    if isinstance(v,str):
        try:return json.loads(v)
        except (ValueError,TypeError):return None
    return v
def fields(n):return {x['field']:x['value'] for x in n.get('fields',[])}
def ok(result):
    if result is None or result.get('native_is_error'):return False
    v=load(fields(result).get('output'))
    return v is not None and not(isinstance(v,dict) and (v.get('error') or v.get('is_error') or v.get('success') is False))
def children(v):
    yield v
    if isinstance(v,dict):
        for x in v.values():yield from children(x)
    elif isinstance(v,list):
        for x in v:yield from children(x)
def eq(a,b):
    # Bool is not a numeric value; do not join "1", 1 and True.
    return type(a)==type(b) and a==b or type(a) in (int,float) and type(b) in (int,float) and a==b
def words(s):return set(re.findall(r'[a-z]{3,}',re.sub(r'([a-z])([A-Z])',r'\1 \2',s).lower()))
def identities(v):
    out=[]
    if isinstance(v,dict):
        for k,x in v.items():
            if ID_KEY.search(k):out.append(x)
            out.extend(identities(x))
    elif isinstance(v,list):
        for x in v:out.extend(identities(x))
    return out
def records(ev):
    ns=[x for x in ev['evidence_view']['nodes'] if x['category']!='episode']
    results={x['result_of']:x for x in ns if x['category']=='tool_result'}
    out=[];cwd=0;account=0
    for c in ns:
        if c['category']!='tool_call':continue
        f=fields(c);tool=f.get('name');args=load(f.get('arguments'));res=results.get(c['id'])
        # Any cd attempt is a conservative context barrier, even if failed.
        if tool=='cd':cwd+=1
        if any(x in (tool or '').lower() for x in ['login','logout','authenticat']):account+=1
        scope=READ_SCOPES.get(tool)
        out.append({'call':c,'result':res,'tool':tool,'args':args,'value':load(fields(res).get('output')) if res else None,
                    'scope':(scope,cwd if scope=='cwd' else account if scope=='account' else 0)})
    return ns,out
def candidates(g,current,kind):
    return evidence_candidates(evidence(g),current,kind,_digest(g))

def evidence_candidates(ev,current,kind,source_hash=None):
    if kind not in ('superseded','corroboration','consumed'):raise ValueError('Unknown relation pruning kind')
    query=json.dumps(current,ensure_ascii=False)
    if HISTORY_QUERY.search(query):return [],{'history_query':1}
    ns,calls=records(ev);actions=[];reasons={};last=calls[-1]['call']['call_group'] if calls else None
    def reject(reason):reasons[reason]=reasons.get(reason,0)+1
    def action(old,other,relation,**rest):
        return {'kind':kind,'relation':relation,'source_call':old['call']['id'],'source_result':old['result']['id'],
                'witness_call':other['call']['id'],'witness_result':other['result']['id'],
                'source_graph_sha256':source_hash,**rest}
    for i,old in enumerate(calls):
        if old['tool'] not in READ_SCOPES or not ok(old['result']) or old['call']['call_group']==last:continue
        later=[x for x in calls[i+1:] if x['call']['ordinal']>old['result']['ordinal'] and ok(x['result'])]
        if kind in ('superseded','corroboration'):
            matches=[x for x in later if x['tool']==old['tool'] and x['scope']==old['scope'] and x['args']==old['args']]
            if not matches:continue
            new=matches[-1];same=eq(old['value'],new['value'])
            if same!=(kind=='corroboration'):continue
            # All old identifier values must remain explicitly accessible elsewhere.
            remaining=[f['value'] for n in ns if n['id'] not in (old['call']['id'],old['result']['id']) for f in n.get('fields',[])]
            retained_values=[a for f in remaining for a in children(load(f) if load(f) is not None else f)]
            if any(not any(eq(v,a) for a in retained_values) for v in identities(old['value'])):reject('unique_identifier');continue
            # Only complete compatible result shapes define a later snapshot.
            if isinstance(old['value'],dict) and (not isinstance(new['value'],dict) or set(old['value'])!=set(new['value'])):
                reject('different_result_shape');continue
            actions.append(action(old,new,'later_same_scoped_read' if not same else 'later_equal_scoped_read',
                                  delete_events=[old['call']['id'],old['result']['id']],value_changed=not same))
            continue
        # Documented stock price -> order price, with the same stock symbol.
        if old['tool']=='get_stock_info' and isinstance(old['value'],dict) and 'price' in old['value']:
            consumers=[x for x in later if x['tool']=='place_order' and isinstance(x['args'],dict)
                       and x['args'].get('symbol')==old['args'].get('symbol')
                       and eq(x['args'].get('price'),old['value']['price'])
                       and isinstance(x['value'],dict) and x['value'].get('order_id') is not None]
            for consumer in consumers[:1]:
                producers=[p for p in calls[:calls.index(consumer)] if p['tool']=='get_stock_info' and ok(p['result'])
                           and p['args']==old['args'] and isinstance(p['value'],dict) and eq(p['value'].get('price'),old['value']['price'])]
                if len(producers)!=1:reject('ambiguous_producer');continue
                keep={'price'};query_words=words(query)
                for k,v in old['value'].items():
                    if ID_KEY.search(k) or identities(v) or words(k)&query_words:keep.add(k)
                    # Protect an entire field if its exact nontrivial value is used later.
                    if any(eq(v,a) for x in later for a in children(x['args'])):keep.add(k)
                remove=sorted(set(old['value'])-keep)
                if not remove:continue
                actions.append(action(old,consumer,'stock_price_used_in_order',remove_keys=remove,consumed_path='/price',argument_path='/price'))
        # A USD quote selected as the operand of a completed currency conversion.
        if old['tool']=='get_flight_cost' and isinstance(old['value'],dict):
            vs=old['value'].get('travel_cost_list')
            if not isinstance(vs,list) or not vs or not all(type(x) in (int,float) for x in vs):continue
            consumers=[x for x in later if x['tool']=='compute_exchange_rate' and isinstance(x['args'],dict)
                       and x['args'].get('base_currency')=='USD' and any(eq(x['args'].get('value'),v) for v in vs)
                       and isinstance(x['value'],dict) and type(x['value'].get('exchanged_value')) in (int,float)]
            if not consumers:continue
            consumer=consumers[-1]
            producers=[p for p in calls[:calls.index(consumer)] if p['tool']=='get_flight_cost' and ok(p['result'])
                       and isinstance(p['value'],dict) and any(eq(consumer['args']['value'],v) for v in p['value'].get('travel_cost_list',[]))]
            if len(producers)!=1:reject('ambiguous_producer');continue
            # Keep every quote value explicitly appearing in any later call argument.
            used=[v for v in vs if any(eq(v,a) for x in later for a in children(x['args']))]
            if len(used)>=len(vs):continue
            actions.append(action(old,consumer,'usd_quote_used_in_conversion',replace_list={'key':'travel_cost_list','retained':used},
                                  consumed_path='/travel_cost_list/*',argument_path='/value'))
    return actions,reasons

def render(g):
    text=full_render(base_graph(g))
    a=g.get('relation_pruning',{})
    if a.get('notice'):text+='\n'+a['notice']
    return text

def apply(g,a,count):
    if _digest(g)!=a['source_graph_sha256']:raise ValueError('Stale relation action')
    source=evidence(g);out=deepcopy(source)
    original={n['id']:deepcopy(n) for n in source['evidence_view']['nodes'] if n['category']!='episode'}
    removed=set(a.get('delete_events',[]));changed=None
    out['evidence_view']['nodes']=[n for n in out['evidence_view']['nodes'] if n['id'] not in removed]
    if a['kind']=='consumed':
        target=next(n for n in out['evidence_view']['nodes'] if n['id']==a['source_result'])
        f=next(f for f in target['fields'] if f['field']=='output');before=load(f['value']);value=deepcopy(before)
        for k in a.get('remove_keys',[]):del value[k]
        if 'replace_list' in a:value[a['replace_list']['key']]=a['replace_list']['retained']
        f['value']=json.dumps(value,ensure_ascii=False,separators=(',',':')) if isinstance(f['value'],str) else value
        f['value_type']=type(f['value']).__name__;changed=deepcopy(target)
    new,mapping=_refresh(out)
    dst={n['id']:n for n in evidence(new)['evidence_view']['nodes'] if n['category']!='episode'}
    for oldid,newid in mapping.items():
        want=deepcopy(changed if changed and oldid==changed['id'] else original[oldid])
        want.update(id=newid,ordinal=dst[newid]['ordinal'])
        if 'result_of' in want:want['result_of']=mapping[want['result_of']]
        if want!=dst[newid]:raise AssertionError('Unexpected retained evidence change')
    if set(mapping)!=set(original)-removed:raise AssertionError('Undeclared event deletion')
    if not audit_record_graph(new)['ok']:raise AssertionError('Invalid derived graph')
    if a['kind']=='consumed':
        notice='Pruned evidence: '+mapping[a['source_result']]+'/output is partial; retained operands were used in '+mapping[a['witness_call']]+'.'
    else:
        notice='Pruned evidence: an earlier read was removed; retained later observation: '+mapping[a['witness_result']]+'.'
    new['relation_pruning']={'version':VERSION,'notice':notice}
    saved=count(full_render(g))-count(render(new))
    if saved<=0:raise ValueError('No positive relation edit saving')
    audit={'version':VERSION,'action':a,'source_graph_sha256':_digest(g),'edited_graph_sha256':_digest(new),
           'saved_tokens':saved,'memory_tokens_before':count(full_render(g)),'memory_tokens_after':count(render(new)),
           'removed_event_ids':sorted(removed),'old_to_new_event_ids':mapping,
           'retained_event_values_exact':True,'retained_json_values_exact':True,
           'retained_output_lexical_json_format':False if changed else True,
           'full_original_evidence_preserved':False,'task_preservation_certified':False,
           'causal_dependency_proven':False}
    # Projection reparses one JSON output; values, not original whitespace, are invariant.
    return new,audit

def prune(g,count,current,*,kind,min_saved_tokens=50):
    if type(min_saved_tokens)is not int or min_saved_tokens<1:raise ValueError('Invalid minimum saving')
    choices=[]
    for a in candidates(g,current,kind)[0]:
        try:out,audit=apply(g,a,count)
        except ValueError as err:
            if str(err)=='No positive relation edit saving':continue
            raise
        if audit['saved_tokens']>=min_saved_tokens:choices.append((out,audit))
    if not choices:raise ValueError('No eligible relation edit')
    return max(choices,key=lambda x:(x[1]['saved_tokens'],x[1]['action']['source_result']))
