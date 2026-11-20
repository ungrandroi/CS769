"""Lossy merge of large numeric-array subtrees into explicit summary nodes.

No task text or tool names are consulted. The first and final32 elements and
exact count/sum/min/max survive. Other individual elements are genuinely omitted.
This is not reversible and must pass behavioral tests before wider use.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
import json,hashlib
from cs769.models.edits.record_edits import evidence, _refresh, _digest, render as render_full
from cs769.models.edits.subtree_share import _index
from cs769.models.graphs.graph_memory_records import audit_record_graph

MIN_ELEMENTS=128
TAIL_ELEMENTS=32
LEGEND=('Objects marked __numeric_series_summary__ replace an original numeric array. '
        'They retain count, sum, min, max, the first element and the final32 elements in order; '
        'other individual elements are omitted.\n')

def array_summary(raw, *, min_elements=128, tail_elements=32, eligibility="decimal_literal"):
    if type(min_elements) is not int or type(tail_elements) is not int or not 0 < tail_elements < min_elements <= 20000:
        raise ValueError("Require 0 < tail_elements < min_elements <= 20000")
    if eligibility not in ("decimal_literal", "noninteger"):
        raise ValueError("Unknown numeric eligibility")
    decimal_notation_seen=[False]
    def decimal_number(token):
        decimal_notation_seen[0]=True
        return Decimal(token)
    a=json.loads(raw,parse_float=decimal_number,parse_int=Decimal)
    if not isinstance(a,list) or not min_elements<=len(a)<=20000:raise ValueError('Array length outside fixed range')
    if not all(isinstance(x,Decimal) and x.is_finite() for x in a):raise ValueError('Not a finite numeric array')
    # Keep pure integer-literal lists protected; decimal notation such as 400.0 is eligible.
    # This is a distinct variant, not the previously validated frozen method.
    if (eligibility == "decimal_literal" and not decimal_notation_seen[0]) or (eligibility == "noninteger" and not any(x != x.to_integral_value() for x in a)):raise ValueError('Pure integer-literal arrays are protected')
    if any(len(str(x))>40 for x in a):raise ValueError('Numeric precision outside exact accumulator bound')
    with localcontext() as ctx:
        ctx.prec=100
        total=sum(a,Decimal(0))
    num=lambda x:format(x,'f')
    parts=['"count":'+str(len(a)),'"sum":'+num(total),'"min":'+num(min(a)),
        '"max":'+num(max(a)),'"first":'+num(a[0]),'"final_start_index":'+str(len(a)-tail_elements),
        '"final_values":['+','.join(num(x) for x in a[-tail_elements:])+']',
        '"omitted_interior_count":'+str(len(a)-tail_elements-1)]
    text='{"__numeric_series_summary__":{'+','.join(parts)+'}}'
    return text,{'count':len(a),'retained_individual_elements':tail_elements+1,
        'omitted_individual_elements':len(a)-tail_elements-1,'original_array_sha256':hashlib.sha256(raw.encode()).hexdigest()}

def merge_series(graph,count, *, min_elements=128, tail_elements=32, eligibility="decimal_literal"):
    assert audit_record_graph(graph)['ok']
    original=evidence(graph);edited_evidence=deepcopy(original)
    events={n['id']:n for n in original['evidence_view']['nodes']}
    nodes,expand,tree=_index(graph)
    protected={n['payload_node'] for n in graph['record_layer']['nodes'] if n['category']=='identifier_occurrence'}
    replacements={};actions=[]
    for field in graph['payload_layer']['fields']:
        if events[field['event_id']]['category']!='tool_result' or field['parse_fallback'] is not None:continue
        for identity in tree(field['root']):
            n=nodes[identity]
            if n['kind']!='array' or protected.intersection(tree(identity)):continue
            try:text,audit=array_summary(expand(identity), min_elements=min_elements, tail_elements=tail_elements, eligibility=eligibility)
            except (ValueError,TypeError):continue
            if count(text)>=count(expand(identity)):continue
            replacements[identity]=text
            actions.append(dict(audit,event_id=field['event_id'],field=field['field'],payload_node=identity,
                span=n['span'],saved_payload_tokens=count(expand(identity))-count(text)))
    if not actions:raise ValueError('No eligible large unreferenced noninteger numeric array')
    def visit(identity):
        if identity in replacements:return replacements[identity]
        n=nodes[identity]
        return n['text'] if 'text' in n else ''.join(visit(c) for c in n['parts'])
    edited_nodes={n['id']:n for n in edited_evidence['evidence_view']['nodes']};changed={}
    for field in graph['payload_layer']['fields']:
        if not any(a['event_id']==field['event_id'] and a['field']==field['field'] for a in actions):continue
        old=expand(field['root']);new=visit(field['root'])
        target=next(f for f in edited_nodes[field['event_id']]['fields'] if f['field']==field['field'])
        assert target['value']==old and isinstance(old,str)
        target['value']=new;changed[(field['event_id'],field['field'])]=new
    edited,mapping=_refresh(edited_evidence)
    # Every unchanged evidence field, call, result relation, message and grouping
    # remains exact. Only declared array spans inside selected outputs differ.
    recovered=evidence(edited);after={n['id']:n for n in recovered['evidence_view']['nodes']}
    for oldid,newid in mapping.items():
        want=deepcopy(events[oldid]);want['id']=newid;want['ordinal']=after[newid]['ordinal']
        if 'result_of' in want:want['result_of']=mapping[want['result_of']]
        for f in want['fields']:
            if (oldid,f['field']) in changed:f['value']=changed[(oldid,f['field'])]
        assert want==after[newid]
    anchors=lambda g:sorted((n for n in g['record_layer']['nodes'] if n['category']=='identifier_anchor'),key=lambda n:n['id'])
    assert anchors(graph)==anchors(edited),'Identifier anchors changed'
    edited['series_merge']={'version':'g9-series-merge-v2-decimal-literals','source_graph_sha256':_digest(graph),
        'min_elements':min_elements,'tail_elements':tail_elements,'eligibility':eligibility,'actions':actions,'full_evidence_preserved':False}
    before=count(render_full(graph));after_count=count(render(edited))
    assert after_count<before
    return edited,{'version':'g9-series-merge-v2-decimal-literals','operation':'merge_series','actions':actions,
        'source_graph_sha256':_digest(graph),'edited_graph_sha256':_digest(edited),
        'memory_tokens_before':before,'memory_tokens_after':after_count,'saved_tokens':before-after_count,
        'full_original_evidence_preserved':False,'restored_graph_exact':False,'retained_evidence_exact':True,
        'all_identifier_anchors_preserved':True,'tool_names_or_task_text_used':False,
        'task_preservation_certified':False,'applied':True}

def render(graph):
    if 'series_merge' not in graph:return render_full(graph)
    g=deepcopy(graph);g.pop('series_merge');assert audit_record_graph(g)['ok']
    text=render_full(g);opening='<memory_graph scope="completed_prior_turns">\n'
    assert text.startswith(opening)
    return opening+LEGEND.replace('final32', 'final'+str(graph['series_merge']['tail_elements']))+text[len(opening):]
