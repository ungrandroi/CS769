"""Paired, independently seeded working-context threshold experiment.

Identity is generated live once; graph branches replay its exact prefix against
fresh BFCL tools. No future actions or official hidden states enter conversion.
"""
import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from types import MethodType

from core.graph_memory_replace import retained_instructions
from core.local_qwen_tokenizer import LocalQwenTokenizer
from core.model_config import MODEL_KEY, SERVING_MODEL
from core.qwen_prompt_accounting import to_chat_tools
from core.qwen_transport import chat_messages, digest, plain, response_from_chat

SAMPLING = dict(temperature=0.6, top_p=0.95, top_k=20, repeat_penalty=1.0)


def write(path, value):
    path.write_text(json.dumps(plain(value), ensure_ascii=False, indent=2) + '\n')


def post(base, route, body):
    request = urllib.request.Request(base.removesuffix('/v1') + route,
                                    data=json.dumps(body).encode(),
                                    headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.load(response)


def request_body(req, seed):
    return dict(model=SERVING_MODEL, messages=chat_messages(req['input']),
                tools=to_chat_tools(req['tools']), **SAMPLING, seed=seed,
                max_tokens=4096, stream=False, cache_prompt=True,
                chat_template_kwargs={'enable_thinking': False, 'preserve_thinking': False})


def template_count(base, body, tok):
    rendered = post(base, '/apply-template', body)
    return tok.count(rendered['prompt'], parse_special=True)


def all_paired(history):
    calls = {m['call_id'] for m in history if m.get('type') == 'function_call'}
    outputs = {m['call_id'] for m in history if m.get('type') == 'function_call_output'}
    return calls == outputs


def content_tokens(history, tok):
    """Secondary content-only audit, not the trigger metric."""
    total = 0
    for m in chat_messages(history):
        if m['role'] in ('system', 'developer'):
            continue
        total += tok.count(m.get('content') or '')
        for c in m.get('tool_calls', []):
            total += tok.count(c['function']['name'] + c['function']['arguments'])
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    parser.add_argument('--category', required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--method', choices=['identity', 'state', 'event', 'dedup'], required=True)
    parser.add_argument('--variant', default='readable')
    parser.add_argument('--explanation', choices=['none', 'minimal', 'full'], default='none')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--identity', type=Path)
    parser.add_argument('--base-url', default='http://127.0.0.1:11436/v1')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert not (out/'manifest.json').exists(), 'Never overwrite an attempt'
    assert (args.method == 'identity') == (args.identity is None)
    os.environ.update(BFCL_PROJECT_ROOT=str(out), OPENAI_API_KEY='local-no-key',
                      OPENAI_BASE_URL=args.base_url)
    os.environ.pop('OPENAI_DEFAULT_HEADERS', None)
    from bfcl_eval.model_handler.api_inference.openai_response import OpenAIResponsesHandler
    from bfcl_eval.utils import load_dataset_entry, make_json_serializable
    from openai.types.responses import Response
    source = source_manifest = None
    boundary = None
    if args.identity:
        source_manifest = json.loads((args.identity/'manifest.json').read_text())
        assert source_manifest['method'] == 'identity'
        assert source_manifest['status'] == 'complete'
        assert source_manifest['seed'] == args.seed
        source = json.loads((args.identity/'api.json').read_text())
        boundary = source_manifest.get('trigger_index')
    manifest = dict(task=args.task, category=args.category, method=args.method,
                    variant=args.variant, explanation=args.explanation,
                    seed=args.seed, sampling=SAMPLING, threshold=1000,
                    threshold_metric='native full minus fixed-only template tokens',
                    base_url=args.base_url, context=131072, max_tokens=4096,
                    identity=str(args.identity) if args.identity else None,
                    status='running', triggered=False, started_at=time.time())
    if source is not None and boundary is None:
        manifest.update(status='not_triggered', inherited_passed=source_manifest['passed'])
        write(out/'manifest.json', manifest)
        return
    handler = OpenAIResponsesHandler(SERVING_MODEL, 0.6, MODEL_KEY, True)
    entry = next(x for x in load_dataset_entry(args.category) if x['id'] == args.task)
    records, accounting = [], []
    turn = 0
    replacement = None
    fixed_cache = {}
    original_fixed = None
    tok = LocalQwenTokenizer()
    def save():
        write(out/'manifest.json', manifest)
        write(out/'api.json', records)
        write(out/'accounting.json', accounting)
    def log(event):
        with (out/'native.jsonl').open('a') as f:
            f.write(json.dumps(plain(event), ensure_ascii=False) + '\n')
    add = handler._add_next_turn_user_message_FC
    def add_user(self, data, user_message):
        nonlocal turn
        turn += 1
        return add(data, user_message)
    handler._add_next_turn_user_message_FC = MethodType(add_user, handler)
    query = handler._query_FC
    def query_fc(self, data):
        nonlocal boundary, replacement, original_fixed
        i = len(records)
        history = plain(data['message'])
        fixed = plain(retained_instructions(history))
        if original_fixed is None:
            original_fixed = fixed
        assert fixed == original_fixed, 'Dynamic system/developer instructions need explicit accounting'
        if source is not None and i < boundary:
            return query(data)
        if source is not None and i == boundary:
            assert history == source[i]['request']['input'], 'Prefix replay changed'
            write(out/'checkpoint-history.json', history)
            assert all_paired(history)
            # Adapter may change, but old frozen records stay immutable.
            from core.optimized_graph import build_memory
            working = [m for m in history if m.get('role') not in ('system', 'developer')]
            method = {'state':'v1-compact', 'event':'v2-compact', 'dedup':'v2-dedup'}[args.method]
            memory, metadata = build_memory(working, method, args.explanation, tok.count)
            (out/'memory.txt').write_text(memory)
            write(out/'memory-metadata.json', metadata)
            data['message'] = [*fixed, {'role':'assistant', 'content':memory}]
            replacement = plain(data['message'])
            manifest.update(triggered=True, trigger_index=i, trigger_turn=turn,
                            checkpoint_sha256=digest(history),
                            source_work_tokens=source_manifest['source_work_tokens'],
                            memory_tokens=tok.count(memory),
                            instruction_tokens=metadata.get('instruction_tokens'),
                            instruction_insertions=1 if metadata.get('instruction_tokens', 0) else 0)
            save()
        return query(data)
    handler._query_FC = MethodType(query_fc, handler)
    def generate(**kwargs):
        nonlocal boundary
        req = plain(kwargs)
        i = len(records)
        if source is not None and i < boundary:
            assert req == source[i]['request'], f'Request differs in replay at {i}'
            record = dict(source[i], source='replay')
            records.append(record)
            return Response.model_validate(record['response']), record['latency']
        if replacement:
            assert req['input'][:len(replacement)] == replacement
        body = request_body(req, args.seed + i * 1000003)
        full_tokens = template_count(args.base_url, body, tok)
        fixed_body = dict(body, messages=chat_messages(retained_instructions(req['input'])))
        fixed_key = digest({'messages':fixed_body['messages'], 'tools':body['tools']})
        if fixed_key not in fixed_cache:
            fixed_body['messages'].append({'role':'user', 'content':''})
            fixed_prompt = post(args.base_url, '/apply-template', fixed_body)['prompt']
            sentinel = '<|im_start|>user\n<|im_end|>\n'
            assert fixed_prompt.count(sentinel) == 1
            fixed_cache[fixed_key] = tok.count(fixed_prompt.replace(sentinel, '', 1), parse_special=True)
        fixed_tokens = fixed_cache[fixed_key]
        work_tokens = full_tokens - fixed_tokens
        assert work_tokens >= 0, 'Invalid fixed-template subtraction'
        acc = dict(index=i, turn=turn, input_tokens=full_tokens, fixed_tokens=fixed_tokens,
                   working_tokens=work_tokens,
                   content_tokens=content_tokens(req['input'], tok), seed=body['seed'])
        if source is None and boundary is None and work_tokens > 1000 and all_paired(req['input']):
            boundary = i
            write(out/'checkpoint-history.json', req['input'])
            manifest.update(triggered=True, trigger_index=i, trigger_turn=turn,
                            checkpoint_sha256=digest(req['input']),
                            source_work_tokens=work_tokens, first_input=full_tokens)
        if i == boundary:
            manifest['first_input'] = full_tokens
        accounting.append(acc)
        if full_tokens + 4096 > 131072:
            raise RuntimeError(f'Runtime context exceeded: {full_tokens}+4096')
        log(dict(event='request', **acc, request=body))
        start = time.monotonic()
        raw = post(args.base_url, '/v1/chat/completions', body)
        elapsed = time.monotonic() - start
        assert raw['model'] == SERVING_MODEL
        assert raw['usage']['prompt_tokens'] == full_tokens
        log(dict(event='response', index=i, turn=turn, latency=elapsed, response=raw))
        response = response_from_chat(raw, i)
        # Bridge uses structural Responses defaults; wire sampling is in body.
        records.append(dict(request=req, response=plain(response), source='live',
                            turn=turn, latency=elapsed))
        save()
        return response, elapsed
    handler.generate_with_backoff = generate
    save()
    try:
        result, metadata = handler.inference(entry, True, False)
        metadata = plain(make_json_serializable(metadata))
        handler.write({'id':args.task, 'result':result, **metadata}, out/'result')
        write(out/'full.json', {'result':plain(result), 'metadata':metadata})
        manifest.update(status='complete', replayed_requests=sum(r['source']=='replay' for r in records),
                        live_requests=sum(r['source']=='live' for r in records))
        from core.qwen_official_score import score_run
        score = score_run(out, {'id':args.task, 'category':args.category})
        manifest['passed'] = score['passed']
    except BaseException as error:
        manifest.update(status='error', error=repr(error))
        raise
    finally:
        manifest['finished_at'] = time.time()
        save()
        tok.close()
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
