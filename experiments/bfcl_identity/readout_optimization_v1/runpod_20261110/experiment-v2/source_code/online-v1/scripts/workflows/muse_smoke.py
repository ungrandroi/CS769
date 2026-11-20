"""Nonbenchmark Muse tool/template checks; records every request and response."""
import json
from pathlib import Path
import time
import urllib.request


def main():
    root = Path(__file__).resolve().parents[2] / 'experiments/bfcl_identity/muse_transfer_v1/runtime/smoke'
    root.mkdir(parents=True, exist_ok=True)
    def post(route, body):
        request = urllib.request.Request('http://127.0.0.1:11437/' + route,
                                         data=json.dumps(body).encode(),
                                         headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)
    def write(name, value):
        (root / name).write_text(json.dumps(value, indent=2) + '\n')
    tool = {'type':'function','function':{'name':'lookup_value',
            'description':'Retrieve the stored integer for a key.',
            'parameters':{'type':'object','properties':{'key':{'type':'string'}},
                          'required':['key']}}}
    fixed = {'role':'system','content':'You are a helpful assistant. Use tools when requested.'}
    history = [fixed, {'role':'user','content':'Use lookup_value to retrieve both alpha and beta, then tell me their sum. Do not guess the stored values.'}]
    common = dict(model='bfcl-muse-glimmer-30b', tools=[tool], temperature=0.6,
                  top_p=0.95, top_k=20, min_p=0.05, repeat_penalty=1.0,
                  max_tokens=4096, stream=False, cache_prompt=True,
                  chat_template_kwargs={'reasoning_strength':'low'})
    fixed_response = post('apply-template', dict(common, messages=[fixed]))
    write('fixed-template.json', fixed_response)
    check = {}
    for add in (False, True):
        for parse in (False, True):
            r=post('tokenize',dict(content=fixed_response['prompt'],add_special=add,parse_special=parse))
            check[f'add_special={add},parse_special={parse}']=r
    write('tokenize-options.json',check)
    obtained=set(); records=[]
    for step in range(6):
        body=dict(common,messages=history,seed=982451653+step)
        write(f'{step}-request.json',body)
        template=post('apply-template',body);write(f'{step}-template.json',template)
        # Muse's runtime adds BOS; rendered prompts require add_special=True.
        tokens=post('tokenize',dict(content=template['prompt'],add_special=True,parse_special=True))
        started=time.time();response=post('v1/chat/completions',body)
        write(f'{step}-response.json',response)
        assert len(tokens['tokens']) == response['usage']['prompt_tokens']
        message=response['choices'][0]['message'];calls=message.get('tool_calls') or []
        record=dict(step=step,seconds=time.time()-started,usage=response.get('usage'),
                    native_template_tokens=len(tokens['tokens']),tool_calls=len(calls),
                    reasoning_characters=len(message.get('reasoning_content') or ''),
                    content=message.get('content'),finish_reason=response['choices'][0]['finish_reason'])
        records.append(record);write('progress.json',records);print(json.dumps(record),flush=True)
        visible={k:v for k,v in message.items() if k in ('role','content','tool_calls')}
        history.append(visible)
        if not calls:
            break
        for call in calls:
            assert call['function']['name']=='lookup_value'
            args=call['function']['arguments'];args=json.loads(args) if isinstance(args,str) else args
            key=args['key'];assert key in ('alpha','beta');obtained.add(key)
            history.append(dict(role='tool',tool_call_id=call['id'],
                                content=json.dumps({'key':key,'value':{'alpha':7,'beta':11}[key]})))
    assert obtained=={'alpha','beta'}, obtained
    assert not calls and '18' in (message.get('content') or ''), message
    # Verify explicit reasoning fields versus visible-history-only policy.
    sentinel='MUSE_REASONING_SENTINEL_93f1'
    probe=[fixed,{'role':'user','content':'test'},
           {'role':'assistant','content':'ok','reasoning_content':sentinel},
           {'role':'user','content':'continue'}]
    supplied=post('apply-template',dict(common,messages=probe))
    probe[2].pop('reasoning_content')
    omitted=post('apply-template',dict(common,messages=probe))
    write('reasoning-history-probe.json',dict(supplied=supplied,omitted=omitted,
          supplied_contains_sentinel=sentinel in supplied['prompt'],
          omitted_contains_sentinel=sentinel in omitted['prompt']))
    write('summary.json',dict(status='passed',records=records,obtained=sorted(obtained),
          fixed_only_render_accepted=True,reasoning_policy='raw responses recorded; reasoning_content excluded from subsequent request messages explicitly'))


if __name__=='__main__':main()
