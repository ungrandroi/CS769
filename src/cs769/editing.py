"""One interface for graph edits; no task IDs, expected answers, or evaluator access."""
from copy import deepcopy
from .registry import register_editor,EDITORS
from .builders import options
from .edits import g9_edit

class Ineligible(ValueError):pass

def deletion(g,count,current,opts):
    from .edits import fine_delete,multi_delete
    options(opts,['count','selection'])
    n=opts.get('count',1);rule=opts.get('selection','oldest')
    if type(n) is not int or n not in (1,2,3):raise ValueError('Deletion count must be 1, 2, or 3')
    actions=fine_delete.candidates(g)
    if len(actions)<=n:raise Ineligible('Deletion must leave a complete interaction')
    if rule=='id_linked':actions,_=multi_delete.order_candidates(g)
    elif rule in ('oldest','recent'):actions=sorted(actions,key=lambda a:a['call_ordinal'],reverse=rule=='recent')
    elif rule=='largest':
        ranked=[]
        for a in actions:
            try:_,check=fine_delete.apply(g,a,count);ranked.append((check['saved_tokens'],a))
            except ValueError:continue
        actions=[a for _,a in sorted(ranked,key=lambda x:(-x[0],x[1]['call_ordinal']))]
    else:raise ValueError('Unknown deletion selection')
    if len(actions)<n:raise Ineligible('Not enough eligible actions')
    result=fine_delete.apply(g,actions[0],count) if n==1 else multi_delete.apply(g,actions[:n],count)
    return *result,g9_edit.render

def coarse(g,count,current,opts):
    options(opts,['kind'])
    kind=opts.get('kind','delete')
    if kind not in ('delete','project'):raise ValueError('Unknown coarse action')
    out,audit=g9_edit.choose(g,kind,count);return out,audit,g9_edit.render

def series(g,count,current,opts):
    from .edits import series_merge
    options(opts,['min_elements','tail_elements','eligibility'])
    out,audit=series_merge.merge_series(g,count,**opts);return out,audit,series_merge.render

def simple(module,function,renderer='render',with_current=False):
    def apply(g,count,current,opts):
        options(opts,[])
        from importlib import import_module
        m=import_module('.edits.'+module,__package__)
        result=getattr(m,function)(g,count,current) if with_current else getattr(m,function)(g,count)
        return *result,getattr(m,renderer)
    return apply

register_editor('delete_interactions',deletion)
register_editor('delete_or_project',coarse)
register_editor('numeric_summary',series)
for name,module,fn,render,current in [
 ('share_observations','share_observations','share','render',False),
 ('share_subtrees','subtree_share','share_subtrees','render',False),
 ('share_schema','schema_share','share_schema','render',False),
 ('share_outputs','conservative_edits','share_all','render',False),
 ('repeat_reads','conservative_edits','repeated_reads','render',False),
 ('ancillary_fields','conservative_edits','ancillary_fields','render',True),
 ('trim_context','field_pruning','trim_context','render',True),
 ('resolved_errors','field_pruning','resolved_errors','render',True)]:
    register_editor(name,simple(module,fn,render,current))

def apply_edits(memory,configs,count,current):
    reports=[];terminal=False
    for spec in configs:
        name=spec['name']
        if not spec.get('enabled',True):reports.append({'name':name,'status':'disabled'});continue
        if name not in EDITORS:raise ValueError('Unknown edit: '+name)
        if terminal:raise ValueError('Sharing/summary must be the last enabled edit; choose order explicitly')
        before=deepcopy(memory.graph)
        try:graph,audit,renderer=EDITORS[name](memory.graph,count,current,spec.get('options',{}))
        except ValueError as error:
            # Only known lack-of-candidate errors may become declared no-ops.
            unavailable=isinstance(error,Ineligible) or str(error).startswith(('No eligible','No positive','No adjacent','No profitable','No same-argument','No rendered','Reference overhead','At least four'))
            if spec.get('on_ineligible','error')!='skip' or not unavailable:raise
            if memory.graph!=before:raise AssertionError('Failed edit mutated source')
            reports.append({'name':name,'status':'ineligible','reason':str(error)});continue
        if memory.graph!=before:raise AssertionError('Edit mutated source')
        memory.graph=graph;memory.render=renderer
        reports.append({'name':name,'status':'applied','audit':audit})
        terminal=any(k in graph for k in ('series_merge','subtree_sharing','sharing_layer','schema_sharing'))
    return reports
