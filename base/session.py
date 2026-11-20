"""Apply a configured intervention once to an externally owned agent history."""
from copy import deepcopy
from cs769.base.history import normalize, checkpoint_reached
from cs769.tasks.memory import prepare

class MemorySession:
    def __init__(self,config,count,*,counter_name='caller_supplied'):
        self.config=config;self.count=count;self.counter_name=counter_name
        self.result=None;self.original=None;self.excluded_reason=None

    def project(self,messages,*,completed_turns=0,prefix_passed=None,native_context=None,native_input_tokens=None,fixed_tokens=None):
        if self.result is not None:
            if messages[:len(self.original)]!=self.original:raise ValueError('Source prefix changed after replacement')
            return deepcopy(self.result['messages'])+deepcopy(messages[len(self.original):])
        if self.excluded_reason:return deepcopy(messages)
        c=self.config;provider='anthropic' if c.model['provider']=='anthropic' else 'openai'
        # Completed-turn checkpoints cut before the next request; working-history
        # checkpoints contain the active request inside the graph exactly once.
        history=messages;following=[]
        if c.checkpoint['kind']=='completed_turn':
            if not messages or messages[-1].get('role')!='user':return deepcopy(messages)
            history=messages[:-1];following=messages[-1:]
        norm,_=normalize(history,provider,c.model.get('old_thinking','omit'))
        if not checkpoint_reached(history if provider!='anthropic' else norm,c.checkpoint,self.count,completed_turns=completed_turns,native_input_tokens=native_input_tokens,fixed_tokens=fixed_tokens):return deepcopy(messages)
        if c.selection.get('require_prefix_pass') and prefix_passed is None:raise ValueError('Need official completed-prefix score for eligibility')
        if c.selection.get('require_prefix_pass') and not prefix_passed:
            self.excluded_reason='prefix_failed';return deepcopy(messages)
        r=prepare(history,c,self.count,native_context=native_context,next_messages=following,counter_name=self.counter_name)
        if not r['eligible']:
            self.excluded_reason='empty_index';return deepcopy(messages)
        self.result=r;self.original=deepcopy(messages)
        return deepcopy(r['messages'])
