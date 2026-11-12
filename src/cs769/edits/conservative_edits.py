"""Success-first candidates. No task answers, future turns, or evaluator access."""
from copy import deepcopy
import json
from .g9_edit import evidence, render as full_render, _refresh, _digest, candidates, apply
from .g9_merge import merge, restore
from .inspect_merge import graph_groups, LEGEND
from cs769.graphs.graph_memory_evidence import render_evidence_segments
from cs769.graphs.graph_memory_records import audit_record_graph

READ_ONLY = {'wc', 'cat', 'ls', 'grep', 'pwd', 'find'}

def share_all(graph, count):
    """Merge disjoint equal-output payload trees, retaining every original event."""
    _, groups = graph_groups(graph)
    chosen=[]
    for tool, ids in groups:
        # Each group must save tokens even after paying the shared legend alone.
        from .g9_merge import render
        try:
            part=merge(graph,ids)
            if count(render(part)) < count(full_render(graph)): chosen.append((tool,ids,part))
        except ValueError: continue
    if not chosen: raise ValueError('No positive-saving exact sharing')
    out=deepcopy(graph); replacements={};aliases=[];events=[]
    for gi,(tool,ids,part) in enumerate(chosen):
        events.extend(ids)
        for n in part['payload_layer']['nodes']:
            if n['kind']=='shared_payload_ref':
                assert n['id'] not in replacements
                n=deepcopy(n);n['alias_group']=f'g{gi}_'+n['alias_group'];replacements[n['id']]=n
        for a in part['sharing_layer']['aliases']:
            a=deepcopy(a);a['alias_group']=f'g{gi}_'+a['alias_group'];aliases.append(a)
    out['payload_layer']['nodes']=[replacements.get(n['id'],n) for n in out['payload_layer']['nodes']]
    out['sharing_layer']={'version':'g9-shared-output-v1','original_graph_sha256':_digest(graph),
                          'event_ids':events,'aliases':aliases}
    assert restore(out)==graph
    text=render_shared(out)
    return out, audit(graph,out,count,text,'share_all',True,{'groups':[ids for _,ids,_ in chosen]})

def render_shared(shared):
    g=restore(shared);e=evidence(g);segments=render_evidence_segments(e)
    full=full_render(g);body=''.join(s['text'] for s in segments);assert full.startswith(body)
    aliases={a['event_id']:a['canonical_event'] for a in shared['sharing_layer']['aliases']}
    spans={s['node_id']:s['text'] for s in segments if s['kind']=='evidence' and s.get('field')=='output'}
    output=[];i=0;expansion=[]
    while i<len(segments):
        if i+2<len(segments):
            s=segments[i+1];event=s.get('node_id')
            if s['kind']=='evidence' and s.get('field')=='output' and event in aliases:
                assert segments[i]['kind']==segments[i+2]['kind']=='label'
                target=aliases[event];assert spans[event]==spans[target]
                output.append(f'output_ref={target}.output\n')
                expansion.extend([segments[i]['text'],spans[target],segments[i+2]['text']]);i+=3;continue
        output.append(segments[i]['text']);expansion.append(segments[i]['text']);i+=1
    assert ''.join(expansion)==body
    output[0]+=LEGEND
    return ''.join(output)+full[len(body):]

def audit(before,after,count,text,kind,lossless,action):
    old=count(full_render(before));new=count(text)
    if new>=old:raise ValueError('No rendered token saving')
    return {'version':'preserve-first-v1','operation':kind,'action':action,
        'source_graph_sha256':_digest(before),'edited_graph_sha256':_digest(after),
        'memory_tokens_before':old,'memory_tokens_after':new,'saved_tokens':old-new,
        'full_original_evidence_preserved':lossless,'retained_evidence_exact':True,
        'task_preservation_certified':False,'applied':True}

def repeated_reads(graph,count):
    """Drop only adjacent identical successful filesystem reads in one episode.

    No user/assistant message, other tool call, or state-changing action can
    intervene; preserve the last complete call+result, not an inferred state.
    """
    source=evidence(graph);records=[n for n in source['evidence_view']['nodes'] if n['category']!='episode']
    def fields(n):return {f['field']:f['value'] for f in n['fields']}
    targets=set();pairs=[]
    for i in range(len(records)-3):
        a,b,c,d=records[i:i+4]
        if [n['category'] for n in (a,b,c,d)]!=['tool_call','tool_result','tool_call','tool_result']:continue
        if b['result_of']!=a['id'] or d['result_of']!=c['id']:continue
        if len({n['episode'] for n in (a,b,c,d)})!=1:continue
        if fields(a)!=fields(c) or fields(b)!=fields(d):continue
        if fields(a).get('name') not in READ_ONLY:continue
        out=fields(b).get('output')
        if b.get('native_is_error') or d.get('native_is_error'):continue
        try: obj=json.loads(out) if isinstance(out,str) else out
        except (ValueError,TypeError):obj=None
        if isinstance(obj,dict) and ('error' in obj or obj.get('success') is False):continue
        targets.update([a['id'],b['id']]);pairs.append([a['id'],b['id'],c['id'],d['id']])
    if not targets:raise ValueError('No adjacent identical successful read pairs')
    e=deepcopy(source);e['evidence_view']['nodes']=[n for n in e['evidence_view']['nodes'] if n['id'] not in targets]
    out,mapping=_refresh(e);assert audit_record_graph(out)['ok']
    src={n['id']:n for n in records};dst={n['id']:n for n in evidence(out)['evidence_view']['nodes'] if n['category']!='episode'}
    assert set(mapping)==set(src)-targets
    for old,new in mapping.items():
        expected=deepcopy(src[old]);expected.update(id=new,ordinal=dst[new]['ordinal'])
        if 'result_of' in expected:expected['result_of']=mapping[expected['result_of']]
        assert expected==dst[new]
    return out,audit(graph,out,count,full_render(out),'repeat_read',False,{'removed_event_ids':sorted(targets),'matching_read_windows':pairs})

def ancillary_fields(graph,count,current):
    """Narrow pre-existing field allowlist; preserve latest two tool exchanges.

    Protect numeric engine state/price fields. Drop only clearly ancillary list
    payloads unless the user names that field/topic. Never change values kept.
    """
    allowed={'post_tweet':{'tags','mentions'},'get_order_details':{'metadata'},
             'estimate_distance':{'intermediaryCities'},'book_flight':{'booking_history'}}
    terms={'tags':['tag','hashtag'],'mentions':['mention'],'metadata':['metadata'],
           'intermediaryCities':['city','cities','route','intermediate'],
           'booking_history':['history','previous','past','booking']}
    query=json.dumps(current,ensure_ascii=False).lower();out=graph;steps=[]
    original_calls=[n for n in evidence(graph)['evidence_view']['nodes'] if n['category']=='tool_call']
    protected_calls={n['call_id'] for n in original_calls[-2:]}
    while True:
        opts=[]
        byid={n['id']:n for n in evidence(out)['evidence_view']['nodes']}
        for action in candidates(out)[1]:
            if action['key'] not in allowed.get(action['tool'],set()):continue
            if byid[action['event_id']]['call_id'] in protected_calls:continue
            if any(t in query for t in terms[action['key']]):continue
            try:
                edited,check=apply(out,action,count);opts.append((edited,check))
            except ValueError:continue
        if not opts:break
        out,check=max(opts,key=lambda x:x[1]['saved_tokens']);steps.append(check)
    if not steps:raise ValueError('No eligible ancillary field')
    return out,audit(graph,out,count,full_render(out),'ancillary_fields',False,{'steps':[s['action'] for s in steps]})

def render(graph):
    return render_shared(graph) if 'sharing_layer' in graph else full_render(graph)
