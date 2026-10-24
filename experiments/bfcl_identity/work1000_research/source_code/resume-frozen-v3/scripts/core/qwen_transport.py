"""Local Qwen Chat/Responses transport; no experimental dataset dependency."""
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
                    ident.startswith(f'qwen_fc_{previous_live_message}_') for ident in call_ids):
                result[-1]['tool_calls'] = msg['tool_calls']
                previous_live_message = None
                continue
        result.append(msg)
        ident = item.get('id', '')
        previous_live_message = ident.removeprefix('qwen_msg_') if ident.startswith('qwen_msg_') else None
    return result


def response_from_chat(raw, index):
    """Lossless tool output/text bridge for the official Responses parser."""
    from openai.types.responses import Response
    choice, = raw['choices']
    msg = choice['message']
    output = []
    if msg.get('content'):
        output.append({'type': 'message', 'id': f'qwen_msg_{index}', 'status': 'completed',
                       'role': 'assistant', 'content': [{'type': 'output_text', 'text': msg['content'], 'annotations': [], 'logprobs': []}]})
    for n, call in enumerate(msg.get('tool_calls') or []):
        output.append({'type': 'function_call', 'id': f'qwen_fc_{index}_{n}',
                       'call_id': f'qwen_call_{index}_{n}', 'name': call['function']['name'],
                       'arguments': call['function']['arguments'], 'status': 'completed'})
    usage = raw['usage']
    return Response.model_validate({'id': f'qwen_response_{index}', 'object': 'response',
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

