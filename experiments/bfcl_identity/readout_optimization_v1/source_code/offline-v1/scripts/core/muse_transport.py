"""Local Muse Chat/Responses transport; no experimental dataset dependency."""
import json
import hashlib
import time
from core.qwen_prompt_accounting import to_chat_messages

def plain(value):
    if hasattr(value, "model_dump"):
        return plain(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True).encode()).hexdigest()

def chat_messages(items):
    """Standard Chat wire objects, retaining exact raw argument JSON."""
    result = []
    previous_live_message = None
    for item in to_chat_messages(items):
        content = item.get('content')
        if isinstance(content, list):
            content = '\n'.join(part['text'] for part in content)
        msg = {'role': item['role'], 'content': content or ''}
        if 'tool_call_id' in item:
            msg['tool_call_id'] = item['tool_call_id']
        if item.get('tool_calls'):
            msg['tool_calls'] = [{'id': call['id'], 'type': 'function', 'function': {
                'name': call['function']['name'],
                'arguments': call['responses_item']['arguments']}}
                for call in item['tool_calls']]
            # Responses carries text and calls as separate output items. A live
            # Chat completion originally emitted both inside one assistant
            # message, so restore that grouping for this bridge's own IDs only.
            # Frozen GPT prefixes keep the exact prior accounting convention.
            call_ids = [c['responses_item'].get('id', '') for c in item['tool_calls']]
            if previous_live_message is not None and all(
                    ident.startswith(f'muse_fc_{previous_live_message}_') for ident in call_ids):
                result[-1]['tool_calls'] = msg['tool_calls']
                previous_live_message = None
                continue
        result.append(msg)
        ident = item.get('id', '')
        previous_live_message = ident.removeprefix('muse_msg_') if ident.startswith('muse_msg_') else None
    return result


def response_from_chat(raw, index):
    """Lossless tool output/text bridge for the official Responses parser."""
    from openai.types.responses import Response
    choice, = raw['choices']
    msg = choice['message']
    output = []
    if msg.get('content'):
        output.append({'type': 'message', 'id': f'muse_msg_{index}', 'status': 'completed',
                       'role': 'assistant', 'content': [{'type': 'output_text', 'text': msg['content'], 'annotations': [], 'logprobs': []}]})
    for n, call in enumerate(msg.get('tool_calls') or []):
        output.append({'type': 'function_call', 'id': f'muse_fc_{index}_{n}',
                       'call_id': f'muse_call_{index}_{n}', 'name': call['function']['name'],
                       'arguments': call['function']['arguments'], 'status': 'completed'})
    usage = raw['usage']
    return Response.model_validate({'id': f'muse_response_{index}', 'object': 'response',
        'created_at': raw.get('created', time.time()), 'status': 'completed', 'error': None,
        'incomplete_details': None, 'instructions': None, 'metadata': {}, 'model': raw['model'],
        'output': output, 'parallel_tool_calls': True, 'temperature': 0, 'tool_choice': 'auto',
        'tools': [], 'top_p': 1, 'usage': {'input_tokens': usage['prompt_tokens'],
        'output_tokens': usage['completion_tokens'], 'total_tokens': usage['total_tokens'],
        'input_tokens_details': {'cached_tokens': usage.get('prompt_tokens_details', {}).get('cached_tokens', 0), 'cache_write_tokens': 0},
        'output_tokens_details': {'reasoning_tokens': usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0)}}})


def prefix_log(log):
    turns, result = 0, []
    for item in log:
        if isinstance(item, dict):
            if turns == 1:
                break
            turns += 1
        result.append(item)
    return result



# Muse produces reasoning, but this registered experiment does not feed it back.
# Raw reasoning is retained in native.jsonl, never converted into visible text.
MODEL_KEY = "local/Muse-Glimmer-30B-Q4-K-XL-FC"
SERVING_MODEL = "bfcl-muse-glimmer-30b"
MODEL_NAME = "Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL"
REASONING_POLICY = "generate_low; raw_reasoning_logged; historical_reasoning_not_reinserted"

def register_models():
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING, ModelConfig
    from bfcl_eval.model_handler.api_inference.openai_completion import OpenAICompletionsHandler
    MODEL_CONFIG_MAPPING.setdefault(MODEL_KEY, ModelConfig(
        model_name=SERVING_MODEL, display_name="Local Muse Glimmer 30B Q4_K_XL (FC)",
        url="https://huggingface.co/meta-models/Muse-Glimmer-30B", org="Meta",
        license="Apache-2.0", model_handler=OpenAICompletionsHandler,
        is_fc_model=True, underscore_to_dot=True))

def post(base, route, body):
    import urllib.request
    request = urllib.request.Request(base.removesuffix('/v1') + route,
        data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.load(response)

class NativeTokenizer:
    """Tokenize through the same loaded Muse model that serves inference."""
    def __init__(self, base):
        self.base = base
        self.cache = {}
    def count(self, text, parse_special=False):
        key = (text, parse_special)
        if key not in self.cache:
            response = post(self.base, '/tokenize', dict(content=text, add_special=parse_special,
                                                       parse_special=parse_special))
            self.cache[key] = len(response['tokens'])
        return self.cache[key]
    def close(self):
        self.cache.clear()

def score_run(directory, task):
    from pathlib import Path
    import subprocess, sys
    score_path = directory / 'official-score.json'
    if score_path.exists():
        return json.loads(score_path.read_text())
    results = list((directory / 'result').rglob(f"*{task['category']}_result.json"))
    assert len(results) == 1
    rows = [json.loads(line) for line in results[0].read_text().splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]['id'] == task['id']
    command = [sys.executable, '-m', 'core.muse_transport', 'evaluate', '--model', MODEL_KEY,
               '--test-category', task['category'], '--partial-eval',
               '--result-dir', str(directory/'result'), '--score-dir', str(directory/'score')]
    with (directory/'official-evaluation.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    paths = list((directory/'score').rglob(f"*{task['category']}_score.json"))
    assert len(paths) == 1
    scores = [json.loads(line) for line in paths[0].read_text().splitlines() if line.strip()]
    assert scores[0]['total_count'] == 1 and scores[0]['correct_count'] in (0,1)
    result = dict(summary=scores[0], passed=bool(scores[0]['correct_count']),
                  diagnostics=[{k:v for k,v in row.items() if k in
                    ('id','valid','error','test_category','model_name')} for row in scores[1:]],
                  result_sha256=hashlib.sha256(results[0].read_bytes()).hexdigest(),
                  score_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                  evaluator='official BFCL', score_file=str(paths[0].relative_to(directory)))
    score_path.write_text(json.dumps(result, indent=2)+'\n')
    return result

if __name__ == '__main__':
    import os
    os.environ['OPENAI_API_KEY'] = 'local-evaluation-no-key'
    os.environ['OPENAI_BASE_URL'] = 'http://127.0.0.1:11437/v1'
    register_models()
    from bfcl_eval.__main__ import cli
    cli()
