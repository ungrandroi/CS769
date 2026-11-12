"""Native Anthropic transport; BFCL's normalized tape is never replay authority."""
from copy import deepcopy
import json
from pathlib import Path
import shlex
import stat
import time
import urllib.error
import urllib.request

MODEL = 'claude-sonnet-5-5'
ENDPOINT = 'https://api.anthropic.com/v1/messages'
RUNTIME = {'max_tokens': 16384, 'thinking': {'type': 'adaptive'},
           'output_config': {'effort': 'high'}, 'tool_choice': {'type': 'auto'}}
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


def credentials(path=None):
    path = Path(path) if path is not None else Path.home()/'.anthropic_env'
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError('Anthropic credential file must have mode 600')
    for line in path.read_text().splitlines():
        stripped = line.strip().removeprefix('export ').strip()
        if '=' not in stripped or stripped.startswith('#'):
            continue
        name, value = stripped.split('=', 1)
        if name.strip() == 'ANTHROPIC_API_KEY':
            parts = shlex.split(value, comments=True)
            if len(parts) == 1 and parts[0]:
                return parts[0]
    raise ValueError('ANTHROPIC_API_KEY missing from credential file')


def post_messages(*args, **kwargs):
    raise PermissionError('Legacy direct API calls are disabled; use the shared authorized budget transport')


def native_tools(tools):
    result = []
    for tool in tools:
        if tool.get('type', 'function') != 'function':
            raise ValueError('Only BFCL client functions are allowed')
        item = {'name': tool['name'], 'input_schema': deepcopy(tool['parameters'])}
        if 'description' in tool:
            item['description'] = tool['description']
        result.append(item)
    return result


def text_blocks(content):
    if isinstance(content, str):
        return [{'type': 'text', 'text': content}]
    result = []
    for block in content:
        if block.get('type') not in ('text', 'input_text', 'output_text'):
            raise ValueError('Unexpected nontext BFCL user/system block')
        result.append({'type': 'text', 'text': block['text']})
    return result


def append_prompt(messages, system, prompts):
    for message in prompts:
        if message['role'] in ('system', 'developer'):
            if messages:
                raise ValueError('BFCL initial system prompt changed mid-conversation')
            system.extend(text_blocks(message['content']))
        elif message['role'] == 'user':
            messages.append({'role': 'user', 'content': text_blocks(message['content'])})
        else:
            raise ValueError('Unexpected BFCL prompt role')


def tool_error(content):
    """Only explicit simulator errors are flagged; keep the original content intact."""
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except (ValueError, TypeError):
        return False
    return isinstance(value, dict) and bool(value.get('error'))


def append_tool_results(messages, outputs, call_ids):
    if len(outputs) != len(call_ids):
        raise ValueError('Tool results do not match tool IDs')
    if not messages or messages[-1]['role'] != 'assistant':
        raise ValueError('Tool results must immediately follow assistant tool use')
    expected = [b['id'] for b in messages[-1]['content'] if b.get('type') == 'tool_use']
    if list(call_ids) != expected:
        raise ValueError('Tool result IDs/order differ from native calls')
    blocks = []
    for output, call_id in zip(outputs, call_ids):
        block = {'type': 'tool_result', 'tool_use_id': call_id, 'content': output}
        if tool_error(output):
            block['is_error'] = True
        blocks.append(block)
    messages.append({'role': 'user', 'content': blocks})


def normalized_response(raw, index):
    """Scoring bridge only. Native content remains intact in the authoritative tape."""
    from openai.types.responses import Response
    if raw.get('model') != MODEL or raw.get('role') != 'assistant':
        raise ValueError('Unexpected Anthropic model or response role')
    output = []
    for n, block in enumerate(raw['content']):
        if block['type'] == 'text':
            output.append({'type': 'message', 'id': f'claude_msg_{index}_{n}',
                           'status': 'completed', 'role': 'assistant',
                           'content': [{'type': 'output_text', 'text': block['text'],
                                        'annotations': [], 'logprobs': []}]})
        elif block['type'] == 'tool_use':
            output.append({'type': 'function_call', 'id': f'claude_fc_{index}_{n}',
                           'call_id': block['id'], 'name': block['name'],
                           'arguments': json.dumps(block['input'], ensure_ascii=False),
                           'status': 'completed'})
    usage = usage_counts(raw.get('usage', {}))
    return Response.model_validate({
        'id': raw['id'], 'object': 'response', 'created_at': 0,
        'status': 'completed', 'error': None, 'incomplete_details': None,
        'instructions': None, 'metadata': {}, 'model': raw['model'], 'output': output,
        'parallel_tool_calls': True, 'temperature': 1, 'tool_choice': 'auto',
        'tools': [], 'top_p': 1, 'usage': {'input_tokens': usage['prompt_tokens'],
        'output_tokens': usage['completion_tokens'], 'total_tokens': usage['total_tokens'],
        'input_tokens_details': {'cached_tokens': usage['cached_input_tokens'],
                                'cache_write_tokens': usage['cache_write_input_tokens']},
        'output_tokens_details': {'reasoning_tokens': 0}}})


def usage_counts(usage):
    # Anthropic input_tokens excludes both cache reads and cache writes.
    cached = usage.get('cache_read_input_tokens', 0)
    created = usage.get('cache_creation_input_tokens', 0)
    input_tokens = usage.get('input_tokens', 0) + cached + created
    output_tokens = usage.get('output_tokens', 0)
    return {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'uncached_input_tokens': usage.get('input_tokens', 0),
            'cached_input_tokens': cached, 'cache_write_input_tokens': created}
