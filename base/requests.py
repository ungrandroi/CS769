"""Provider request formatting only; credentials and network are external."""
from copy import deepcopy

def build_request(prepared, tools):
    cfg=prepared['config'];model=cfg['model'];sampling=deepcopy(model.get('sampling',{}))
    if set(sampling)&{'messages','tools','model','system'}:raise ValueError('Sampling cannot replace request data')
    messages=deepcopy(prepared['messages'])
    if model['provider']=='anthropic':
        if 'seed' in sampling:raise ValueError('Anthropic has no seed parameter; omit it explicitly')
        system=[];body=[]
        for m in messages:
            if m['role'] in ('system','developer'):system.append({'type':'text','text':m['content']})
            else:body.append(m)
        return dict(model=model['name'],system=system,messages=body,tools=deepcopy(tools),**sampling)
    return dict(model=model['name'],messages=messages,tools=deepcopy(tools),**sampling)
