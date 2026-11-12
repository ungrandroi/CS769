"""Dependency-injected continuation. Environment owns tools and unchanged official eval.

No provider/network implementation is bundled. A caller must explicitly supply
an authorized transport and persistent budget accounting; dry runs need neither.
"""
from copy import deepcopy
from typing import Protocol
from .requests import build_request
from .metrics import Usage

class Environment(Protocol):
    def step(self, assistant_message:dict) -> list: ...
    def finished(self) -> bool: ...
    def evaluate(self) -> dict: ...

class Transport(Protocol):
    def send(self, request:dict) -> dict: ...

class Budget(Protocol):
    def reserve(self, request:dict) -> str: ...
    def settle(self, reservation:str, response:dict) -> None: ...
    def uncertain(self, reservation:str) -> None: ...

def continue_run(prepared, tools, environment, transport, budget, *, authorized=False, emit=None):
    """Resume an ALREADY replay-verified environment. Each successful response is logged.

    An environment step appends matching tool returns and, when appropriate,
    the next original user turn. It must never alter the official evaluator.
    Runtime errors are returned as errors, never fabricated task failures.
    """
    if not authorized:raise PermissionError('Paid continuation requires explicit authorization')
    cfg=prepared['config'];cap=cfg['execution']['budget_usd']
    if cap<=0:raise PermissionError('Set an explicitly approved positive API budget')
    if not prepared['eligible']:raise ValueError('Checkpoint excluded by frozen selection')
    # The injected persistent accountant must enforce THIS experiment cap.
    if getattr(budget,'limit_usd',None)!=cap:raise ValueError('Budget limit differs from approved config')
    owner=getattr(transport,'budget_owner',None)
    if owner is not None and owner is not budget:raise ValueError('Transport and runtime use different budget owners')
    provider=cfg['model']['provider'];state=deepcopy(prepared);usage=Usage();emit=emit or (lambda event:None)
    for index in range(cfg['execution'].get('max_requests',30)):
        if environment.finished():break
        req=build_request(state,tools);reservation=budget.reserve(req) if owner is None else None
        try:resp=transport.send(req)
        except BaseException:
            if reservation is not None:budget.uncertain(reservation)
            raise
        if reservation is not None:budget.settle(reservation,resp)
        usage.add(resp,provider)
        emit({'event':'request_response','index':index,'request':req,'response':resp})
        if provider=='anthropic':message={'role':'assistant','content':resp['content']}
        else:message=deepcopy(resp['choices'][0]['message'])
        state['messages'].append(message)
        state['messages'].extend(environment.step(deepcopy(message)))
    complete=environment.finished()
    score=environment.evaluate() if complete else None
    if complete and (not isinstance(score,dict) or type(score.get('passed')) is not bool):raise ValueError('Official adapter must return a binary passed result')
    return {'status':'complete' if complete else 'request_limit','score':score,'usage':usage.report(),'messages':state['messages']}
