from copy import deepcopy
import json

def dumps(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def normalize(messages, provider='openai', old_thinking='omit'):
    """Convert supported visible text/tool records, fail on unhandled media."""
    clean=[];normalized=[]
    for msg in deepcopy(messages):
        if msg.get('type')=='reasoning':
            continue  # Not visible evidence; callers retain the original archive.
        if provider=='anthropic' and isinstance(msg.get('content'),list):
            blocks=msg['content']; kept=[];calls=[];texts=[];results=[]
            for b in blocks:
                kind=b.get('type')
                if kind in ('thinking','redacted_thinking'):
                    if old_thinking=='preserve':kept.append(b)
                    continue
                if kind=='text': texts.append(b['text'])
                elif kind=='tool_use':calls.append({'id':b['id'],'type':'function','function':{'name':b['name'],'arguments':dumps(b['input'])}})
                elif kind=='tool_result':
                    content=b['content']
                    if isinstance(content,list):
                        if any(x.get('type')!='text' for x in content):raise ValueError('Non-text tool result unsupported')
                        content='\n'.join(x['text'] for x in content)
                    results.append({'role':'tool','tool_call_id':b['tool_use_id'],'content':content})
                else:raise ValueError('Unsupported Anthropic block '+str(kind))
                kept.append(b)
            if kept:clean.append({**msg,'content':kept})
            if texts or calls:
                row={'role':msg['role'],'content':'\n'.join(texts)}
                if calls:row['tool_calls']=calls
                normalized.append(row)
            normalized.extend(results)
        elif msg.get('type')=='function_call':
            row={'role':'assistant','content':None,'tool_calls':[{'id':msg['call_id'],'type':'function','function':{'name':msg['name'],'arguments':msg['arguments']}}]}
            clean.append(row);normalized.append(deepcopy(row))
        elif msg.get('type')=='function_call_output':
            row={'role':'tool','tool_call_id':msg['call_id'],'content':msg['output']};clean.append(row);normalized.append(deepcopy(row))
        else:
            if isinstance(msg.get('content'),list):
                if any(b.get('type') not in ('text','input_text','output_text') for b in msg['content']):raise ValueError('Unsupported message content')
                msg['content']=''.join(b['text'] for b in msg['content'])
            if msg.get('role') not in ('system','developer','user','assistant','tool'):raise ValueError('Unsupported message role')
            clean.append(msg);normalized.append(deepcopy(msg))
    return normalized,clean

def balanced(history):
    seen=set();pending=set();returned=set()
    for m in history:
        for call in m.get('tool_calls',[]) or []:
            identity=call.get('id')
            if not isinstance(identity,str) or identity in seen:return False
            seen.add(identity);pending.add(identity)
        if m.get('role')=='tool':
            identity=m.get('tool_call_id')
            if identity not in pending or identity in returned:return False
            pending.remove(identity);returned.add(identity)
    return not pending

def checkpoint_reached(history, config, count, *, completed_turns=0, native_input_tokens=None, fixed_tokens=None):
    normalized,_=normalize(history) if any(m.get('type') in ('function_call','function_call_output') for m in history) else (history,history)
    if not balanced(normalized):return False
    kind=config['kind']
    if kind=='manual':return True
    if kind=='completed_turn':return completed_turns>=config['turns']
    mode=config['counter'];visible=[m for m in normalized if m.get('role') not in ('system','developer')]
    if mode=='history_json':n=count(dumps(visible))
    elif mode=='history_json_sorted':n=count(history_counter_text(history,sort_keys=True))
    elif mode=='tool_payload':n=count(dumps([m for m in visible if m.get('role')=='tool' or m.get('tool_calls')]))
    else:
        if native_input_tokens is None or fixed_tokens is None:raise ValueError('native_minus_fixed needs measured native input and fixed overhead')
        n=native_input_tokens-fixed_tokens
        if n<0:raise ValueError('Negative working input count')
    return n>config['threshold'] if config.get('strict',True) else n>=config['threshold']

def evidence_history(messages):
    """Canonical visible records used by all graph/edit modules.

    Keep existing Responses records as-is. Chat call grouping remains in the
    separate native history and is validated by the evidence builder.
    """
    out=[]
    for m in deepcopy(messages):
        if m.get('type') in ('function_call','function_call_output'):
            out.append(m);continue
        calls=m.get('tool_calls') or []
        if calls:
            if m.get('content'):out.append({k:v for k,v in m.items() if k!='tool_calls'})
            for c in calls:out.append({'type':'function_call','call_id':c['id'],'name':c['function']['name'],'arguments':c['function']['arguments']})
        elif m.get('role')=='tool':out.append({'type':'function_call_output','call_id':m['tool_call_id'],'output':m['content']})
        else:out.append(m)
    return out

def history_counter_text(messages, *, sort_keys=False):
    """Approved history-only Chat JSON; tools/definitions stay outside this counter."""
    from .adapters.qwen_transport import chat_messages
    if any(m.get("tool_calls") or m.get("role")=="tool" for m in messages):
        chat=[{k:v for k,v in m.items()if k not in ("id","status","type","phase")}for m in messages]
    else:chat=chat_messages(messages)
    visible=[m for m in chat if m.get("role") not in ("system","developer")]
    return json.dumps(visible,ensure_ascii=False,sort_keys=sort_keys,separators=(",",":"),allow_nan=False)
