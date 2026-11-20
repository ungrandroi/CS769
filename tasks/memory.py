"""目的和主要功能：准备图记忆、配置投喂并交付命令结果文件。

适用范围：离线历史准备与正式轨迹的记忆接入，共用同一构图和编辑实现。
"""
from copy import deepcopy
import hashlib
from cs769.base.config import ExperimentConfig, load_config
from cs769.base.history import normalize, balanced, dumps, evidence_history
from cs769.base.registry import BUILDERS
from cs769.models import builders
from cs769.models.editing import apply_edits

def prepare(history, config, count, *, native_history=None, native_context=None, next_messages=None, counter_name='caller_supplied'):
    cfg=config if isinstance(config,ExperimentConfig) else ExperimentConfig.from_dict(config)
    cfg.validate();original=deepcopy(history)
    provider=cfg.model['provider'];normalize_provider='openai' if provider=='qwen' else provider
    if native_history is None:
        norm,native=normalize(history,normalize_provider,cfg.model.get('old_thinking','omit'))
    else:
        norm,_=normalize(history,'openai');_,native=normalize(native_history,normalize_provider,cfg.model.get('old_thinking','omit'))
    if not balanced(norm):raise ValueError('All tool calls need distinct matching results before intervention')
    instructions=[m for m in native if m.get('role') in ('system','developer')]
    graph_source=history if any(m.get('type') in ('function_call','function_call_output') for m in history) else norm
    visible=[m for m in evidence_history(graph_source) if m.get('role') not in ('system','developer')]
    native_visible=[m for m in native if m.get('role') not in ('system','developer')]
    following=deepcopy(next_messages or [])
    if any(m.get('role')!='user' for m in following):raise ValueError('Only new user messages may follow the checkpoint')
    kind=cfg.memory['kind']
    if kind not in BUILDERS:raise ValueError('Unknown memory builder: '+kind)
    opt=deepcopy(cfg.memory.get('options',{}))
    if kind=='readable':opt.setdefault('format','readable')
    memory=BUILDERS[kind](visible,native_visible,normalize_provider,native_context,opt,count)
    original_text=memory.render(memory.graph)
    current=following or next((m for m in reversed(visible) if m.get('role')=='user'),{})
    audits=apply_edits(memory,cfg.edits,count,current)
    if memory.messages is not None and audits:raise ValueError('Partitioned memory cannot use edit renderers')
    text=memory.render(memory.graph);mode=cfg.delivery['mode']
    if mode=='native':projected=deepcopy(native)+following
    elif mode=='replace':
        replacement=memory.messages if memory.messages is not None else [{'role':cfg.delivery.get('role','user'),'content':text}]
        projected=deepcopy(instructions)+deepcopy(replacement)+following
    elif mode=='append':projected=deepcopy(native)+([{'role':cfg.delivery.get('role','assistant'),'content':text}] if text else [])+following
    else:
        if len(following)!=1 or not isinstance(following[0].get('content'),str):raise ValueError('prepend_user requires one new plain-text user message')
        block=('<application_memory source="harness" snapshot="after_checkpoint">\n'+text+'</application_memory>\n\n') if text else ''
        following[0]['content']=block+following[0]['content'];projected=deepcopy(native)+following
    if history!=original:raise AssertionError('Source history mutated')
    return {'config':cfg.to_dict(),'messages':projected,'memory_text':text,'graph':memory.graph,
        'audits':memory.audits,'edits':audits,'source_sha256':hashlib.sha256(dumps(original).encode()).hexdigest(),
        'metrics':{'counter':counter_name,'source_history_json_units':count(dumps(native_visible)),
                   'full_memory_units':count(original_text),'edited_memory_units':count(text),
                   'memory_saved_units':count(original_text)-count(text),
                   'projected_messages_json_units':count(dumps(projected))},
        'eligible':not(cfg.selection.get('require_nonempty_index',False) and not text)}


def prepare_files(config,history,output,*,counter_name="o200k_base",native_history=None,context=None,next_messages=None):
    """Prepare and save one memory through the same path used by the command."""
    from pathlib import Path
    from cs769.base.io import read, write_new, counter
    output=Path(output)
    if output.exists():raise FileExistsError("Output exists")
    cfg=load_config(config)
    if cfg.memory.get("options",{}).get("semantics")=="mixed":
        from cs769.base.bootstrap import ensure_bfcl
        ensure_bfcl()
    optional=lambda path:read(path) if path else None
    result=prepare(read(history),cfg,counter(counter_name),native_history=optional(native_history),
                   native_context=optional(context),next_messages=optional(next_messages),counter_name=counter_name)
    output.mkdir(parents=True)
    for name,value in (("result",result),("config",cfg.to_dict()),("messages",result["messages"]),("graph",result["graph"])):
        write_new(output/(name+".json"),value)
    (output/"memory.txt").write_text(result["memory_text"])
    return {"output":str(output),"eligible":result["eligible"],"metrics":result["metrics"]}
