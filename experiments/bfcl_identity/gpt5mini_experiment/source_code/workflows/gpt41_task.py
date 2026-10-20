"""All-GPT (Azure) BFCL execution, sharing only a GPT-generated first turn."""
from core.research_modes import method_id
import argparse
import json
import os
from pathlib import Path
import time
from types import MethodType
import urllib.error
import urllib.request
import tiktoken
from core.qwen_transport import plain, digest, chat_messages, response_from_chat, prefix_log
from core.qwen_prompt_accounting import to_chat_tools
from core.graph_memory_replace import retained_instructions, assert_replacement_request
from core.research_modes import MODES
from core.model_config import azure_model_key
from workflows.baseline_task import TOOLS, make_memory
import core.qwen_prompt_accounting as _accounting

def _last_duplicate_key(pairs):
    """JSON keeps the last repeated key. The shared parser rejects them, which aborts a turn."""
    return dict(pairs)

_accounting._no_duplicate_keys = _last_duplicate_key

ENV_FILE = Path(os.environ.get('GPT41_ENV_FILE', str(Path.home()/'.azure_openai_env')))
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
MEMORY_TOKENIZER = 'tiktoken o200k_base'


def azure_credentials(path=ENV_FILE):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix('export ').strip()
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"\'')
    return values['OPENAI_BASE_URL'].rstrip('/'), values['OPENAI_API_KEY']


def post_chat(base_url, key, body, attempts=8):
    data = json.dumps(body).encode()
    for attempt in range(attempts):
        request = urllib.request.Request(base_url+'/chat/completions', data=data,
            headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        try:
            with urllib.request.urlopen(request, timeout=600) as f:
                return json.load(f), attempt
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors='replace')[:2000]
            if error.code not in RETRY_STATUS or attempt == attempts-1:
                raise RuntimeError(f'Azure HTTP {error.code}: {detail}') from None
            try:delay = float(error.headers.get('retry-after') or 0)
            except ValueError:delay = 0
            delay = delay or min(60, 5*2**attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == attempts-1:raise
            delay = min(60, 5*2**attempt)
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--category', required=True, choices=('multi_turn_base','multi_turn_long_context'))
    parser.add_argument('--mode', required=True, type=method_id, choices=MODES)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix-source', type=Path)
    parser.add_argument('--deployment', default='gpt-4.1')
    parser.add_argument('--reasoning-effort', choices=('minimal','low','medium','high'))
    args = parser.parse_args()
    assert (args.mode == 'identity') == (args.prefix_source is None)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    assert not (out/'manifest.json').exists(), 'Refuse overwriting an attempt'
    base_url, key = azure_credentials()
    registry = azure_model_key(args.deployment)
    os.environ['BFCL_PROJECT_ROOT'] = str(out)
    # The BFCL handler never reaches Azure: generate_with_backoff is replaced below.
    os.environ['OPENAI_API_KEY'] = 'unused-no-key'; os.environ['OPENAI_BASE_URL'] = 'http://127.0.0.1:9/v1'
    os.environ.pop('OPENAI_DEFAULT_HEADERS', None)
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry, make_json_serializable
    from openai.types.responses import Response
    handler = OpenAIResponsesHandler(args.deployment, 0, registry, True)
    entry = next(x for x in load_dataset_entry(args.category) if x['id'] == args.task_id)
    encoding = tiktoken.get_encoding('o200k_base')
    def count(text):return len(encoding.encode(text, disallowed_special=()))
    source_tape = source_full = None
    prefix_count = None
    if args.prefix_source:
        source_tape = json.loads((args.prefix_source/f'{args.task_id}.api.json').read_text())
        source_full = json.loads((args.prefix_source/f'{args.task_id}.full.json').read_text())
        source_manifest = json.loads((args.prefix_source/'manifest.json').read_text())
        assert source_manifest['mode'] == 'identity' and source_manifest['agent_deployment'] == args.deployment
        assert all(r['source'] == 'live_gpt' for r in source_tape)
        prefix_count = source_manifest['first_turn_requests']
    # Reasoning models reject temperature 0 and count reasoning tokens against the output limit.
    sampling = ({'reasoning_effort':args.reasoning_effort,'max_completion_tokens':16384,'seed':42} if args.reasoning_effort
                else {'temperature':0,'seed':42,'max_tokens':4096})
    records, responses, served = [], [], set()
    turn, reached, replacement, history = 0, False, None, None
    tools_signature = None
    manifest = {'task_id':args.task_id,'category':args.category,'mode':args.mode,'status':'running',
                'agent_deployment':args.deployment,'registry_name':registry,'base_url':base_url,
                'prefix_source':str(args.prefix_source.resolve()) if args.prefix_source else None,
                'runtime':sampling,'memory_tokenizer':MEMORY_TOKENIZER,
                'intervention':'One history replacement before second user input; later history retained'}
    def save():
        (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    def log(path, record):
        with (out/path).open('a') as f:f.write(json.dumps(plain(record),ensure_ascii=False)+'\n')
    save()
    add = handler._add_next_turn_user_message_FC
    def add_user(self, data, user_message):
        nonlocal turn, reached, replacement, history, prefix_count
        turn += 1
        if turn == 1:
            reached = True; history = plain(data['message'])
            if source_tape is not None:
                assert len(records) == prefix_count
                assert history == json.loads((args.prefix_source/'prefix-history.json').read_text())
            else:prefix_count = len(records)
            (out/'prefix-history.json').write_text(json.dumps(history,ensure_ascii=False))
            before = digest(history)
            if args.mode != 'identity':
                memory, graph = make_memory(data['message'], args.mode, count)
                manifest['memory_tokens'] = count(memory)
                (out/f'{args.task_id}.graph.json').write_text(json.dumps(graph,ensure_ascii=False))
                (out/f'{args.task_id}.memory.txt').write_text(memory)
                data['message'] = [*retained_instructions(data['message']), {'role':'assistant','content':memory}]
                replacement = plain(data['message'])
            manifest['boundary'] = {'turn':1,'history_sha256':before,'after_sha256':digest(data['message']),
                                    'source_messages':len(history),'roundtrip_verified':args.mode!='identity'}
            save()
        return add(data,user_message)
    handler._add_next_turn_user_message_FC = MethodType(add_user,handler)
    def generate(**kwargs):
        nonlocal tools_signature
        request = plain(kwargs); index = len(records)
        assert request['model'] == args.deployment
        assert {t['name'] for t in request['tools']} == TOOLS
        signature = digest(request['tools'])
        if tools_signature is None:tools_signature=signature
        assert tools_signature == signature
        if source_tape is not None and not reached:
            assert index < prefix_count and request == source_tape[index]['request']
            response = Response.model_validate(source_tape[index]['response']);latency=source_tape[index]['latency'];origin='gpt_prefix_replay'
        else:
            if replacement is not None:assert_replacement_request(request,replacement,history)
            native={'model':args.deployment,'messages':chat_messages(request['input']),'tools':to_chat_tools(request['tools']),**sampling}
            log('native.jsonl',{'event':'request','index':index,'turn':turn,'request':native})
            started=time.monotonic();raw,retries=post_chat(base_url,key,native)
            latency=time.monotonic()-started
            served.add(raw['model'])
            log('native.jsonl',{'event':'response','index':index,'turn':turn,'latency':latency,'retries':retries,'response':raw})
            responses.append({'turn':turn,'response':raw});response=response_from_chat(raw,index);origin='live_gpt'
        record={'request':request,'response':plain(response),'latency':latency,'source':origin,'turn':turn}
        records.append(record);log(f'{args.task_id}.api.jsonl',record)
        return response,latency
    handler.generate_with_backoff=generate
    try:
        result,metadata=handler.inference(entry,True,False);metadata=plain(make_json_serializable(metadata))
        if source_full is not None:
            assert prefix_log(metadata['inference_log'])==prefix_log(source_full['metadata']['inference_log'])
            assert reached==source_manifest['boundary_reached']
            assert sum(r['source']=='gpt_prefix_replay' for r in records)==prefix_count
        if prefix_count is None:prefix_count=len(records)
        handler.write({'id':args.task_id,'result':result,**metadata},out/'result')
        (out/f'{args.task_id}.full.json').write_text(json.dumps(plain({'result':result,'metadata':metadata}),ensure_ascii=False))
        (out/f'{args.task_id}.api.json').write_text(json.dumps(records,ensure_ascii=False))
        def usage(rs):return {k:sum(r['response']['usage'][k] for r in rs) for k in ('prompt_tokens','completion_tokens','total_tokens')}
        def cached(rs):return sum((r['response']['usage'].get('prompt_tokens_details') or {}).get('cached_tokens',0) for r in rs)
        def reasoning(rs):return sum((r['response']['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens',0) for r in rs)
        manifest.update(status='complete' if reached else 'not_reached',boundary_reached=reached,first_turn_requests=prefix_count,
                        served_models=sorted(served),live_requests=len(responses),
                        replayed_requests=sum(r['source']=='gpt_prefix_replay' for r in records),
                        continuation_requests=sum(r['turn']>0 for r in responses),live_usage=usage(responses),live_cached_input=cached(responses),
                        live_reasoning_output=reasoning(responses),
                        length_truncations=sum(r['response']['choices'][0]['finish_reason']=='length' for r in responses),
                        prefix_usage=usage([r for r in responses if r['turn']==0]),continuation_usage=usage([r for r in responses if r['turn']>0]),
                        prefix_log_equal=True,tools_sha256=tools_signature)
    except BaseException as error:
        manifest.update(status='error',error=f'{type(error).__name__}: {error}');save();raise
    save();print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
