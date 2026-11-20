"""One interface for graph edits; no task IDs, expected answers, or evaluator access."""
from copy import deepcopy
from cs769.base.registry import register_editor, EDITORS
from cs769.models.builders import options
from cs769.models.edits import record_edits

class Ineligible(ValueError):pass

def deletion(g,count,current,opts):
    from cs769.models.edits import fine_delete, multi_delete
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
    return *result,record_edits.render

def coarse(g,count,current,opts):
    options(opts,['kind'])
    kind=opts.get('kind','delete')
    if kind not in ('delete','project'):raise ValueError('Unknown coarse action')
    out,audit=record_edits.choose(g,kind,count);return out,audit,record_edits.render

def series(g,count,current,opts):
    from cs769.models.edits import series_merge
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

def prune_observation(g,count,current,opts):
    from cs769.models.edits import observation_pruning
    options(opts,['min_saved_tokens'])
    out,audit=observation_pruning.prune(g,count,current,**opts)
    return out,audit,record_edits.render

register_editor('prune_observation',prune_observation)
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

def share_structure(g,count,current,opts):
    """Choose exact subtree or schema sharing by measured rendered savings."""
    from cs769.models.edits import subtree_share, schema_share
    options(opts,[])
    choices=[];considered=[]
    for name,module,fn in [
        ('share_subtrees',subtree_share,subtree_share.share_subtrees),
        ('share_schema',schema_share,schema_share.share_schema)]:
        try:out,audit=fn(g,count)
        except ValueError as error:
            if not str(error).startswith(('No eligible','No profitable','Reference overhead','Schema overhead')):
                raise
            considered.append({'operation':name,'eligible':False,'reason':str(error)})
            continue
        if module.restore(out)!=g:raise AssertionError('Shared graph restoration failed')
        considered.append({'operation':name,'eligible':True,'saved_tokens':audit['saved_tokens']})
        choices.append((audit['saved_tokens'],name,out,audit,module.render))
    if not choices:raise Ineligible('No eligible exact structural sharing')
    _,name,out,audit,renderer=max(choices,key=lambda x:(x[0],x[1]))
    audit=deepcopy(audit)
    audit['selection_policy']={'version':'g9-share-structure-v1','rule':'maximum_measured_savings_then_operation_name',
                               'selected':name,'candidates':considered,'uses_task_text':False}
    return out,audit,renderer

register_editor('share_structure',share_structure)

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
        terminal=name in ('prune_witnessed_history','prune_general_history','prune_dependency_fields','contract_dependency_component') or any(k in graph for k in ('series_merge','subtree_sharing','sharing_layer','schema_sharing','relation_pruning'))
    return reports


def prune_relations(g,count,current,opts):
    from cs769.models.edits import relation_pruning
    options(opts,['kind','min_saved_tokens'])
    out,audit=relation_pruning.prune(g,count,current,**opts)
    return out,audit,relation_pruning.render

register_editor('prune_relations',prune_relations)


def prune_booking_receipt(g,count,current,opts):
    from cs769.models.edits import booking_receipt
    options(opts,['min_saved_tokens'])
    out,audit=booking_receipt.prune(g,count,current,**opts)
    return out,audit,booking_receipt.render

register_editor('prune_booking_receipt',prune_booking_receipt)


def prune_derived_evidence(g,count,current,opts):
    from cs769.models.edits import derived_evidence
    options(opts,['kind','min_saved_tokens'])
    out,audit=derived_evidence.prune(g,count,current,**opts)
    return out,audit,derived_evidence.render

register_editor('prune_derived_evidence',prune_derived_evidence)


def prune_witnessed_history(g,count,current,opts):
    from cs769.models.edits import witness_pruning
    options(opts,['relations','min_saved_tokens','resolved_contracts'])
    return witness_pruning.prune(g,count,current,**opts)

register_editor('prune_witnessed_history',prune_witnessed_history)


def prune_general_history(g,count,current,opts):
    from cs769.models.edits import general_pruning
    options(opts,["min_saved_tokens"])
    return general_pruning.prune(g,count,current,**opts)

register_editor("prune_general_history",prune_general_history)


def prune_dependency_fields(g,count,current,opts):
    from cs769.models.edits import dependency_projection
    options(opts,["decision"])
    return dependency_projection.prune(g,count,current,**opts)

register_editor("prune_dependency_fields",prune_dependency_fields)


def contract_dependency_component(g,count,current,opts):
    from cs769.models.edits import component_contraction
    options(opts,["minimum_saving"])
    return component_contraction.contract(g,count,current,**opts)

register_editor("contract_dependency_component",contract_dependency_component)


def contract_observation_state(g,count,current,opts):
    from cs769.models.edits import observation_state_components
    options(opts,["kind","minimum_saving"])
    return observation_state_components.contract(g,count,current,**opts)

register_editor("contract_observation_state",contract_observation_state)


def compact_graph(g,count,current,opts):
    from cs769.models.edits import compact_graph as module
    options(opts,[])
    return module.compact(g,count,current)

def contract_state_chain(g,count,current,opts):
    from cs769.models.edits import state_chain
    options(opts,[])
    return state_chain.contract(g,count,current)

register_editor("compact_graph",compact_graph)
register_editor("contract_state_chain",contract_state_chain)


def paired_graph(g,count,current,opts):
    from cs769.models.edits import paired_graph as module
    options(opts,[])
    return module.compact(g,count,current)

def paired_state_chain(g,count,current,opts):
    from cs769.models.edits import paired_graph as module
    options(opts,[])
    return module.contract(g,count,current)

register_editor("paired_graph",paired_graph)
register_editor("paired_state_chain",paired_state_chain)


def prune_dependency_slice(g,count,current,opts):
    from cs769.models.edits import dependency_slice
    options(opts,["decision"])
    return dependency_slice.prune(g,count,current,**opts)

register_editor("prune_dependency_slice",prune_dependency_slice)
