"""Field-granular pruning and resolved-error removal; development hypotheses."""
import json
from copy import deepcopy
from cs769.models.edits import record_edits
from cs769.models.edits.record_edits import evidence, _refresh, _digest
from cs769.models.edits.conservative_edits import audit, render

# Never remove a primary price, pressure, location, status, ID or call argument.
FIELDS={
 'get_stock_info':{'MA(5)','MA(20)'},
 'get_order_details':{'metadata'},
 'estimate_distance':{'intermediaryCities'},
 'check_tire_pressure':{'car_info'},
 'displayCarStatus':{'metadata'},
 'activateParkingBrake':{'parkingBrakeInstruction'},
 'book_flight':{'booking_history'},
}
GUARDS={
 'get_stock_info':['moving','average','histor','trend','ma(','ma5','ma20'],
 'get_order_details':['metadata'],
 'estimate_distance':['city','cities','route','intermediate'],
 'check_tire_pressure':['manual','model','manufactur','specif','description','car info'],
 'displayCarStatus':['metadata','manual','model','manufactur','specif','description'],
 'activateParkingBrake':['instruction','how to','how do','manual','explain'],
 'book_flight':['history','previous','past'],
}

def trim_context(graph,count,current):
    query=json.dumps(current,ensure_ascii=False).lower();out=graph;steps=[]
    while True:
        options=[]
        for action in record_edits.candidates(out, FIELDS)[1]:
            if any(w in query for w in GUARDS[action['tool']]):continue
            try:changed,check=record_edits.apply(out,action,count,project_fields=FIELDS)
            except ValueError:continue
            if check['saved_tokens']>=100:options.append((changed,check))
        if not options:break
        out,check=max(options,key=lambda x:x[1]['saved_tokens']);steps.append(check)
    if not steps:raise ValueError('No eligible >=100-token contextual field')
    return out,audit(graph,out,count,render(out),'trim_context',False,{'steps':[s['action'] for s in steps]})

def resolved_errors(graph,count,current):
    query=json.dumps(current,ensure_ascii=False).lower()
    if any(w in query for w in ['error','failed','failure','attempt','retry','why']):raise ValueError('Current user refers to errors')
    e=evidence(graph);nodes=[n for n in e['evidence_view']['nodes'] if n['category']!='episode'];byid={n['id']:n for n in nodes}
    calls=[n for n in nodes if n['category']=='tool_call'];results={n['result_of']:n for n in nodes if n['category']=='tool_result'}
    def failed(n):
        if n.get('native_is_error'):return True
        try:
            v=n['fields'][0]['value'];v=json.loads(v) if isinstance(v,str) else v
        except (ValueError,TypeError):return None
        if not isinstance(v,dict):return None
        return bool(v.get('error')) or v.get('success') is False
    targets=set();proof=[]
    for i,c in enumerate(calls):
        r=results[c['id']]
        if failed(r) is not True:continue
        for later in calls[i+1:]:
            if later['episode']!=c['episode']:break
            if later['fields']==c['fields'] and failed(results[later['id']]) is False:
                targets.update([c['id'],r['id']]);proof.append({'removed':[c['id'],r['id']],'later_success':later['id']});break
    if not targets:raise ValueError('No same-argument error resolved later in same episode')
    x=deepcopy(e);x['evidence_view']['nodes']=[n for n in x['evidence_view']['nodes'] if n['id'] not in targets]
    out,mapping=_refresh(x);dst={n['id']:n for n in evidence(out)['evidence_view']['nodes'] if n['category']!='episode'}
    for old,new in mapping.items():
        expected=deepcopy(byid[old]);expected.update(id=new,ordinal=dst[new]['ordinal'])
        if 'result_of' in expected:expected['result_of']=mapping[expected['result_of']]
        assert dst[new]==expected
    return out,audit(graph,out,count,render(out),'resolved_errors',False,{'proof':proof,'removed_event_ids':sorted(targets)})
