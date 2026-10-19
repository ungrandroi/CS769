"""All-Qwen official BFCL execution, sharing only a Qwen-generated first turn."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from types import MethodType
import urllib.request
from urllib.parse import urlparse
from qwen_transport import plain, digest, chat_messages, response_from_chat, prefix_log
from qwen_prompt_accounting import to_chat_tools
from graph_memory_replace import GraphMemoryReplacement, GraphMemoryV2Replacement, retained_instructions, assert_replacement_request
from graph_memory_serialization_target import encode_compact
from graph_memory_serialization import decode_compact, normalize
from local_qwen_tokenizer import LocalQwenTokenizer
from research_modes import MODES
from evaluate_qwen_compact import MODEL_KEY, SERVING_MODEL

TOOLS = set('cat cd cp diff du echo find grep ls mkdir mv pwd rm rmdir sort tail touch wc'.split())


def make_memory(history, mode, count):
    builder = (GraphMemoryReplacement if mode == 'v1-compact' else GraphMemoryV2Replacement)()
    before = digest(history)
    builder.compress(history)
    first, second, payload = builder.render().split('\n', 2)
    graph = json.loads(payload)
    compact = encode_compact(graph, count)
    assert normalize(decode_compact(compact)) == normalize(graph)
    assert digest(history) == before
    return first + '\n' + second + '\n' + compact, builder.graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--category', required=True, choices=('multi_turn_base','multi_turn_long_context'))
    parser.add_argument('--mode', required=True, choices=MODES)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix-source', type=Path)
    parser.add_argument('--base-url', default='http://127.0.0.1:11435/v1')
    args = parser.parse_args()
    assert urlparse(args.base_url).hostname in ('localhost','127.0.0.1','::1')
    assert (args.mode == 'identity') == (args.prefix_source is None)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    assert not (out/'manifest.json').exists(), 'Refuse overwriting an attempt'
    os.environ['BFCL_PROJECT_ROOT'] = str(out)
    os.environ['OPENAI_API_KEY'] = 'local-no-key'; os.environ['OPENAI_BASE_URL'] = args.base_url
    os.environ.pop('OPENAI_DEFAULT_HEADERS', None)
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry, make_json_serializable
    from openai.types.responses import Response
    handler = OpenAIResponsesHandler(SERVING_MODEL, 0, MODEL_KEY, True)
    entry = next(x for x in load_dataset_entry(args.category) if x['id'] == args.task_id)
    source_tape = source_full = None
    prefix_count = None
    if args.prefix_source:
        source_tape = json.loads((args.prefix_source/f'{args.task_id}.api.json').read_text())
        source_full = json.loads((args.prefix_source/f'{args.task_id}.full.json').read_text())
        source_manifest = json.loads((args.prefix_source/'manifest.json').read_text())
        assert source_manifest['mode'] == 'identity' and source_manifest['prefix_model'] == SERVING_MODEL
        assert all(r['source'] == 'live_local_qwen' for r in source_tape)
        prefix_count = source_manifest['first_turn_requests']
    records, responses = [], []
    turn, reached, replacement, history = 0, False, None, None
    tools_signature = None
    manifest = {'task_id':args.task_id,'category':args.category,'mode':args.mode,'status':'running',
                'prefix_model':SERVING_MODEL,'serving_model':SERVING_MODEL,'base_url':args.base_url,
                'prefix_source':str(args.prefix_source.resolve()) if args.prefix_source else None,
                'runtime':{'temperature':0,'seed':42,'max_tokens':4096,'context_size':131072,'thinking':False,'cache_prompt':True},
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
                with LocalQwenTokenizer() as tokenizer:
                    memory, graph = make_memory(data['message'], args.mode, tokenizer.count)
                    manifest['memory_tokens'] = tokenizer.count(memory)
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
        assert request['model'] == SERVING_MODEL
        assert {t['name'] for t in request['tools']} == TOOLS
        signature = digest(request['tools'])
        if tools_signature is None:tools_signature=signature
        assert tools_signature == signature
        if source_tape is not None and not reached:
            assert index < prefix_count and request == source_tape[index]['request']
            response = Response.model_validate(source_tape[index]['response']);latency=source_tape[index]['latency'];origin='qwen_prefix_replay'
        else:
            if replacement is not None:assert_replacement_request(request,replacement,history)
            native={'model':SERVING_MODEL,'messages':chat_messages(request['input']),'tools':to_chat_tools(request['tools']),
                    'temperature':0,'seed':42,'max_tokens':4096,'stream':False,'cache_prompt':True,
                    'chat_template_kwargs':{'enable_thinking':False,'preserve_thinking':False}}
            log('native.jsonl',{'event':'request','index':index,'turn':turn,'request':native})
            started=time.monotonic();req=urllib.request.Request(args.base_url+'/chat/completions',data=json.dumps(native).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=3600) as f:raw=json.load(f)
            latency=time.monotonic()-started
            assert raw['model']==SERVING_MODEL
            log('native.jsonl',{'event':'response','index':index,'turn':turn,'latency':latency,'response':raw})
            responses.append({'turn':turn,'response':raw});response=response_from_chat(raw,index);origin='live_local_qwen'
        record={'request':request,'response':plain(response),'latency':latency,'source':origin,'turn':turn}
        records.append(record);log(f'{args.task_id}.api.jsonl',record)
        return response,latency
    handler.generate_with_backoff=generate
    try:
        result,metadata=handler.inference(entry,True,False);metadata=plain(make_json_serializable(metadata))
        if source_full is not None:
            assert prefix_log(metadata['inference_log'])==prefix_log(source_full['metadata']['inference_log'])
            assert reached==source_manifest['boundary_reached']
            assert sum(r['source']=='qwen_prefix_replay' for r in records)==prefix_count
        if prefix_count is None:prefix_count=len(records)
        handler.write({'id':args.task_id,'result':result,**metadata},out/'result')
        (out/f'{args.task_id}.full.json').write_text(json.dumps(plain({'result':result,'metadata':metadata}),ensure_ascii=False))
        (out/f'{args.task_id}.api.json').write_text(json.dumps(records,ensure_ascii=False))
        def usage(rs):return {k:sum(r['response']['usage'][k] for r in rs) for k in ('prompt_tokens','completion_tokens','total_tokens')}
        manifest.update(status='complete' if reached else 'not_reached',boundary_reached=reached,first_turn_requests=prefix_count,
                        live_requests=len(responses),replayed_requests=sum(r['source']=='qwen_prefix_replay' for r in records),
                        continuation_requests=sum(r['turn']>0 for r in responses),live_usage=usage(responses),
                        prefix_usage=usage([r for r in responses if r['turn']==0]),continuation_usage=usage([r for r in responses if r['turn']>0]),
                        prefix_log_equal=True,tools_sha256=tools_signature)
    except BaseException as error:
        manifest.update(status='error',error=f'{type(error).__name__}: {error}');save();raise
    save();print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
