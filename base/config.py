"""Serializable experiment settings, independent of task IDs and implementation copies."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

@dataclass
class ExperimentConfig:
    version: int = 1
    name: str = 'evidence_graph'
    memory: dict = field(default_factory=lambda: {'kind':'evidence_graph', 'options':{}})
    edits: list = field(default_factory=list)
    delivery: dict = field(default_factory=lambda: {'mode':'replace','role':'user'})
    checkpoint: dict = field(default_factory=lambda: {'kind':'history_tokens','threshold':1000,'counter':'history_json','strict':True})
    model: dict = field(default_factory=lambda: {'provider':'openai','name':'gpt-4.1','sampling':{'temperature':0,'seed':42,'max_tokens':4096},'old_thinking':'omit'})
    selection: dict = field(default_factory=lambda: {'require_prefix_pass':False,'require_nonempty_index':False})
    evaluation: dict = field(default_factory=lambda: {'adapter':'external_official','changed':False})
    execution: dict = field(default_factory=lambda: {'repeats':1,'order_seed':42,'max_requests':30,'budget_usd':0.0})

    def validate(self):
        if type(self.version) is not int or self.version != 1: raise ValueError('Unsupported config version')
        for name in ('memory','delivery','checkpoint','model','selection','evaluation','execution'):
            if not isinstance(getattr(self,name),dict): raise ValueError(name+' must be an object')
        # Older saved configurations used this identifier for the evidence graph.
        if self.memory.get('kind')=='g9':
            self.memory={**self.memory,'kind':'evidence_graph'}
        allowed={
            'memory':{'kind','options'}, 'delivery':{'mode','role'},
            'checkpoint':{'kind','turns','threshold','counter','strict'},
            'model':{'provider','name','sampling','old_thinking'},
            'selection':{'require_prefix_pass','require_nonempty_index'},
            'evaluation':{'adapter','changed'},
            'execution':{'repeats','order_seed','max_requests','budget_usd'}}
        for name,keys in allowed.items():
            extra=set(getattr(self,name))-keys
            if extra:raise ValueError('Unknown '+name+' options: '+', '.join(sorted(extra)))
        if not isinstance(self.memory.get('kind'),str):raise ValueError('Memory kind must be a string')
        if not isinstance(self.memory.get('options',{}),dict):raise ValueError('Memory options must be an object')
        if not isinstance(self.edits,list):raise ValueError('Edits must be a list')
        if not isinstance(self.model.get('sampling',{}),dict):raise ValueError('Sampling must be an object')
        sampling = self.model.get('sampling', {})
        if sampling.get('reasoning_effort') and 'temperature' in sampling:
            raise ValueError('Reasoning sampling must omit temperature')
        if 'temperature' in sampling:
            import math
            value = sampling['temperature']
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 2:
                raise ValueError('Temperature must be finite and between 0 and 2')
        for key,value in self.selection.items():
            if type(value) is not bool:raise ValueError('Selection flags must be boolean')
        if type(self.checkpoint.get('strict',True)) is not bool:raise ValueError('strict must be boolean')
        for key in ('repeats','max_requests'):
            if type(self.execution.get(key)) is not int or self.execution[key]<1:raise ValueError('Invalid execution '+key)
        if self.delivery.get('mode') not in ('replace','native','append','prepend_user'):raise ValueError('Unknown delivery mode')
        if self.delivery.get('role','user') not in ('user','assistant'):raise ValueError('Memory carrier must be user or assistant')
        if self.memory.get('kind')=='identity' and (self.edits or self.delivery.get('mode')!='native'):raise ValueError('Identity must use native delivery without edits')
        if self.delivery.get('mode')=='native' and self.memory.get('kind')!='identity':raise ValueError('Native delivery requires identity')
        if self.delivery.get('mode') in ('append','prepend_user') and self.memory.get('kind')!='native_index':raise ValueError('Only explicit historical B/index profiles may attach native history')
        if self.evaluation != {'adapter':'external_official','changed':False}:raise ValueError('Evaluation is supplied unchanged by the external environment adapter')
        if self.model.get('provider') not in ('openai','anthropic','qwen'):raise ValueError('Unknown provider')
        if self.model.get('old_thinking','omit') not in ('omit','preserve'):raise ValueError('Unknown thinking policy')
        if self.model.get('provider')=='anthropic' and self.model.get('old_thinking')=='preserve' and self.memory.get('kind')!='identity':raise ValueError('Signed thinking cannot be moved into graph memory')
        cp=self.checkpoint
        if cp.get('kind') not in ('completed_turn','history_tokens','manual'):raise ValueError('Unknown checkpoint kind')
        if cp.get('kind')=='history_tokens' and (type(cp.get('threshold')) is not int or cp['threshold']<0):raise ValueError('Invalid token threshold')
        if cp.get('kind')=='completed_turn' and (type(cp.get('turns')) is not int or cp['turns']<1):raise ValueError('Invalid turn count')
        if cp.get('kind')=='history_tokens' and cp.get('counter') not in ('history_json','history_json_sorted','tool_payload','native_minus_fixed'):raise ValueError('Unknown checkpoint counter')
        for e in self.edits:
            if not isinstance(e,dict) or set(e)-{'name','enabled','options','on_ineligible'}:raise ValueError('Invalid edit configuration')
            if not isinstance(e.get('name'),str) or type(e.get('enabled',True)) is not bool:raise ValueError('Invalid edit name/enabled')
            if e.get('on_ineligible','error') not in ('error','skip'):raise ValueError('Unknown edit failure policy')
            if not isinstance(e.get('options',{}),dict):raise ValueError('Edit options must be an object')
        if self.memory.get('kind')!='evidence_graph' and any(e.get('enabled',True) for e in self.edits):raise ValueError('Built-in edits require evidence graph')
        import math
        budget=self.execution.get('budget_usd',0)
        if type(budget) not in (int,float) or not math.isfinite(budget) or budget<0:raise ValueError('Invalid budget')
        return self

    def to_dict(self):return deepcopy(asdict(self))

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict):raise ValueError('Configuration must be an object')
        unknown=set(value)-set(cls.__dataclass_fields__)
        if unknown:raise ValueError('Unknown config keys: '+', '.join(sorted(unknown)))
        return cls(**deepcopy(value)).validate()

def load_config(path):
    def merge(base,patch):
        out=deepcopy(base)
        for key,value in patch.items():
            out[key]=merge(out[key],value) if key not in ('sampling','checkpoint') and isinstance(value,dict) and isinstance(out.get(key),dict) else deepcopy(value)
        return out
    def read(p,seen):
        p=p.resolve()
        if p in seen:raise ValueError('Configuration inheritance cycle')
        data=json.loads(p.read_text())
        if not isinstance(data,dict):raise ValueError('Configuration must be an object')
        parent=data.pop('extends',None)
        if parent is not None:
            if not isinstance(parent,str):raise ValueError('extends must be a path')
            data=merge(read(p.parent/parent,seen|{p}),data)
        return data
    return ExperimentConfig.from_dict(read(Path(path),set()))
