"""Visible-return adapters for a separately versioned mixed-domain experiment.

No simulator/task/GT state is read. Public catalogs and implementation hashes pin
method identities/contracts. Raw messages stay in the builders' source history.
"""
import ast
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

REGISTRY_VERSION = 'bfcl-mixed-observations-1'
MODULES = {'GorillaFileSystem': 'gorilla_file_system', 'TwitterAPI': 'posting_api',
           'MessageAPI': 'message_api', 'TicketAPI': 'ticket_api', 'MathAPI': 'math_api'}
# Filled from the pinned public catalogs and contracts during adapter development.
PINNED_SHA256 = {'data/multi_turn_func_doc/gorilla_file_system.json': 'c4c1b741c71e2a17c97a5dc9c4a91d89978c4eaece56494d14272d5df6c650e9', 'eval_checker/multi_turn_eval/func_source_code/gorilla_file_system.py': '84173750930b09aaa31b90547c9bd79ce75714682608b35e78a9c1ea259faf2b', 'data/multi_turn_func_doc/posting_api.json': '87f9fc404a06e4107d7c366f1399c596440e84c16cb119faf374b2f532d86e8b', 'eval_checker/multi_turn_eval/func_source_code/posting_api.py': '32b887aaa37c7167ad9c84ddfa7bbb855c75d3c1edab19ba868aba29acc4cfa1', 'data/multi_turn_func_doc/message_api.json': '4d58ea933a5d2b280d7a52366617fb47fecd333d7b0e08e724db6fa12fb5f847', 'eval_checker/multi_turn_eval/func_source_code/message_api.py': 'cf72af1635654147af17df1891a7fb354549e78a61930139f741a31f4be21121', 'data/multi_turn_func_doc/ticket_api.json': '31324e0380782664fe82ba05bd23517808ad55692b45a5fe7c3d4d395fe4f0f8', 'eval_checker/multi_turn_eval/func_source_code/ticket_api.py': '6a9375aa6425410c07a151aef27f3e44e9ed1023bb5cc5c25f14f4a9b3c99116', 'data/multi_turn_func_doc/math_api.json': '83fa31708c89442bdcf12ac4dfbe3be8663ec9183a1b1524a9fda98164bc7e0b', 'eval_checker/multi_turn_eval/func_source_code/math_api.py': 'abde32cc25e71b2ff3acf4d028a3c005b98409c174aba4abddbfe1c018afb9a8'}
READS = {
    'GorillaFileSystem': {'pwd','ls','cat','find','wc','sort','grep','du','tail','diff'},
    'TwitterAPI': {'posting_get_login_status','get_tweet','get_user_tweets','search_tweets',
                   'get_tweet_comments','get_user_stats','list_all_following'},
    'MessageAPI': {'list_users','get_user_id','message_get_login_status','view_messages_sent','search_messages','get_message_stats'},
    'TicketAPI': {'get_ticket','ticket_get_login_status','get_user_tickets'},
}


def _json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        return False
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_safe(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_json_safe(v) for v in value)
    return type(value) in (str, int, float, bool) or value is None


def parse_visible_return(raw):
    """Parse JSON or BFCL's literal list repr without executing text; otherwise retain it."""
    if not isinstance(raw, str):
        return deepcopy(raw) if _json_safe(raw) else str(raw)
    if raw == 'None':
        return None
    try:
        parsed = json.loads(raw)
        if _json_safe(parsed):
            return parsed
    except (ValueError, TypeError, RecursionError):
        pass
    if raw.startswith(('[', '{', '(')) and len(raw) <= 5_000_000:
        try:
            parsed = ast.literal_eval(raw)
            if _json_safe(parsed):
                return parsed
        except (ValueError, SyntaxError, TypeError, RecursionError, MemoryError):
            pass
    return raw


def entity_id(domain, entity_type, local_id):
    if type(local_id) not in (str, int):
        raise ValueError('Entity identifiers must be observed string/integer IDs')
    return domain + ':' + entity_type + ':' + json.dumps(local_id, ensure_ascii=False, separators=(',', ':'))


def _vendor_root():
    for root in (Path(__file__).resolve().parents[2], Path.cwd()):
        candidate = root / 'vendor/gorilla/berkeley-function-call-leaderboard/bfcl_eval'
        if candidate.is_dir():
            return candidate
    raise RuntimeError('Pinned BFCL catalogs are unavailable')


@lru_cache(maxsize=1)
def registry():
    root, tools, hashes = _vendor_root(), {}, {}
    for domain, module in MODULES.items():
        for relative in (f'data/multi_turn_func_doc/{module}.json',
                         f'eval_checker/multi_turn_eval/func_source_code/{module}.py'):
            path = root / relative
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if PINNED_SHA256.get(relative) != actual:
                raise RuntimeError(f'Unrecognized mixed-domain contract: {relative}')
            hashes[relative] = actual
        for line in (root / f'data/multi_turn_func_doc/{module}.json').read_text().splitlines():
            if not line.strip(): continue
            doc = json.loads(line)
            name = doc['name']
            if name in tools: raise ValueError(f'Ambiguous tool name: {name}')
            tools[name] = {'domain': domain, 'method': name,
                           'footprint': 'read' if domain == 'MathAPI' or name in READS.get(domain,set()) else 'write'}
    return {'version': REGISTRY_VERSION, 'tools': tools, 'source_sha256': hashes}


def tool_spec(tool):
    public = registry()['tools']
    if tool in public:
        return deepcopy(public[tool])
    if isinstance(tool, str) and '.' in tool:
        domain, name = tool.split('.', 1)
        if name in public and public[name]['domain'] == domain:
            return deepcopy(public[name])
    return {'domain': 'Unknown', 'method': tool, 'footprint': 'unknown'}


def domain_effect(tool, args, raw):
    """Return only evidence-backed domain updates; no history or private state input.

    ``updates`` have stable entity IDs and field values. ``invalidations`` retire
    current assertions, not historical evidence. Operation-specific deletion is
    deliberately non-identifying when the API does not disclose deleted IDs.
    """
    spec = tool_spec(tool)
    domain, method = spec['domain'], spec['method']
    args = args if isinstance(args, dict) else {}
    output = parse_visible_return(raw)
    effect = {'domain': domain, 'method': method, 'status': 'unknown', 'error': None,
              'basis': REGISTRY_VERSION + ':unrecognized_return', 'coverage': 'unmodeled',
              'footprint': spec['footprint'], 'updates': [], 'invalidations': [],
              'observations': [], 'operation': {}, 'parsed_output': deepcopy(output)}

    def accept(status='success', coverage='modeled', basis='documented_return'):
        effect.update(status=status, coverage=coverage, basis=f'{REGISTRY_VERSION}:{method}:{basis}')

    def update(kind, identity, fields):
        effect['updates'].append({'entity':entity_id(domain,kind,identity),'fields':deepcopy(fields)})

    def invalidate(entity=None, fields=None, reason='observed_mutation'):
        effect['invalidations'].append({'domain':domain,'entity':entity,'fields':fields,'reason':reason})

    def observe(kind, value):
        effect['observations'].append({'kind':kind,'value':deepcopy(value)})

    def failure(message, basis):
        effect.update(status='error', error=deepcopy(message), coverage='observation_only',
                      basis=f'{REGISTRY_VERSION}:{method}:{basis}')
        if domain == 'Unknown':
            effect['invalidations'].append({'domain':None,'entity':None,'fields':None,'reason':'unknown_tool_effect'})
        return effect

    # Error wrappers are transport/execution observations, not domain facts.
    if isinstance(raw,str) and raw.startswith('Error during execution:'):
        return failure(raw, 'executor_exception')
    if isinstance(output,dict) and output.get('error'):
        return failure(output['error'], 'top_level_error')
    if method == 'get_user_tickets' and isinstance(output,list) and len(output)==1 and isinstance(output[0],dict) and output[0].get('error'):
        return failure(output[0]['error'], 'ticket_error_list')
    if domain == 'Unknown':
        effect['invalidations'].append({'domain':None,'entity':None,'fields':None,'reason':'unknown_tool_effect'})
        return effect

    if domain == 'GorillaFileSystem':
        if isinstance(output,dict) and output.get('success') is False:
            return failure('Tool reported success=false','success_false')
        expected = {'pwd':'current_working_directory','ls':'current_directory_content','cat':'file_content',
                    'find':'matches','wc':'count','sort':'sorted_content','grep':'matching_lines',
                    'du':'disk_usage','tail':'last_lines','diff':'diff_lines','mv':'result','cp':'result','rm':'result','rmdir':'result'}
        valid = (method in ('mkdir','touch') and output is None
                 or method=='echo' and (output is None or not args.get('file_name'))
                 or method=='cd' and isinstance(output,dict) and (output=={} or isinstance(output.get('current_working_directory'),str))
                 or method in expected and isinstance(output,dict) and expected[method] in output)
        if valid: accept(coverage='filesystem_adapter')
        elif effect['footprint']=='write': invalidate(reason='unrecognized_filesystem_mutation')
        return effect

    out = output if isinstance(output,dict) else {}
    login_fields = {'authenticate_twitter':'authentication_status','message_login':'login_status','ticket_login':'success'}
    if method in login_fields and type(out.get(login_fields[method])) is bool:
        if not out[login_fields[method]]:
            return failure('Authentication attempt rejected; prior session state is unchanged','authentication_rejected')
        fields = {'authenticated':True}
        # User identifiers are useful; passwords/tokens are never semantic facts.
        who = args.get('user_id') if domain=='MessageAPI' else args.get('username')
        if isinstance(who,str): fields['user_id' if domain=='MessageAPI' else 'username']=who
        invalidate(entity_id(domain,'session','current'), reason='successful_login_replaces_session_view')
        update('session','current',fields); accept(); return effect
    if method in ('posting_get_login_status','message_get_login_status','ticket_get_login_status') and type(out.get('login_status')) is bool:
        update('session','current',{'authenticated':out['login_status']})
        if not out['login_status']:
            invalidate(entity_id(domain,'session','current'), ['username','user_id'], 'observed_logged_out')
        accept(); return effect
    if method=='logout' and type(out.get('success')) is bool:
        update('session','current',{'authenticated':False})
        invalidate(entity_id(domain,'session','current'), ['username','user_id'], 'logged_out')
        accept('success' if out['success'] else 'noop',basis='logout_outcome'); return effect

    if domain=='MathAPI' and 'result' in out:
        observe('calculation_result', {'tool':method,'result':out['result']})
        accept(coverage='observation_only'); return effect

    if domain=='TwitterAPI':
        tweet_fields={'id','username','content','tags','mentions'}
        if method in ('post_tweet','get_tweet') and type(out.get('id')) in (int,str):
            update('tweet',out['id'],{**{k:v for k,v in out.items() if k in tweet_fields},'exists':True})
            accept(); return effect
        if method in ('get_user_tweets','search_tweets') and isinstance(output,list) and all(isinstance(row,dict) and type(row.get('id')) in (int,str) for row in output):
            for row in output:update('tweet',row['id'],{**{k:v for k,v in row.items() if k in tweet_fields},'exists':True})
            observe('returned_tweet_ids',[row['id'] for row in output]); accept(); return effect
        if method=='get_tweet_comments' and isinstance(output,list) and type(args.get('tweet_id')) in (str,int):
            update('tweet',args['tweet_id'],{'comments':output}); accept(); return effect
        if method=='mention' and out.get('mention_status')=='Users mentioned successfully' and type(args.get('tweet_id')) in (str,int):
            invalidate(entity_id(domain,'tweet',args['tweet_id']),['mentions'],'mention_added_without_full_list')
            observe('mentions_added',{'tweet_id':args['tweet_id'],'mentions':args.get('mentioned_usernames',[])})
            accept(); return effect
        if method=='comment' and out.get('comment_status')=='Comment added successfully' and type(args.get('tweet_id')) in (str,int):
            invalidate(entity_id(domain,'tweet',args['tweet_id']),['comments'],'comment_added_without_full_list')
            observe('comment_added',{'tweet_id':args['tweet_id'],'content':args.get('comment_content')})
            accept(); return effect
        if method in ('follow_user','unfollow_user'):
            key='follow_status' if method=='follow_user' else 'unfollow_status'
            if type(out.get(key)) is bool:
                # Snapshot invalidation only. The implicit actor may change across login calls.
                invalidate(entity_id(domain,'session','current'),['following_list'],'following_changed_or_reconfirmed')
                observe('following_operation',{'method':method,'target':args.get('username_to_follow',args.get('username_to_unfollow')),'changed':out[key]})
                accept('success' if out[key] else 'noop',coverage='observation_only');return effect
        if method=='list_all_following' and isinstance(out.get('following_list'),list):
            update('session','current',{'following_list':out['following_list']});accept();return effect
        if method=='get_user_stats' and all(k in out for k in ('tweet_count','following_count','retweet_count')):
            observe('user_stats_snapshot',out);accept(coverage='observation_only');return effect
        if method=='retweet' and out.get('retweet_status') in ('Successfully retweeted','Already retweeted'):
            observe('retweet_operation',{'tweet_id':args.get('tweet_id'),'outcome':out['retweet_status']})
            accept('noop' if out['retweet_status']=='Already retweeted' else 'success',coverage='observation_only');return effect

    if domain=='MessageAPI':
        if method in ('get_user_id','add_contact') and isinstance(out.get('user_id'),str):
            if method=='add_contact' and out.get('added_status') is not True: pass
            else:
                fields={'user_id':out['user_id']}
                name=args.get('user',args.get('user_name'))
                if isinstance(name,str):fields['name']=name
                update('user',out['user_id'],fields);accept();return effect
        if method=='send_message' and out.get('sent_status') is True:
            identifier=out.get('message_id')
            if isinstance(identifier,dict) and set(identifier)=={'new_id'}:identifier=identifier['new_id']
            if type(identifier) in (str,int):
                fields={'message_id':identifier,'sent':True,'exists':True}
                if isinstance(args.get('receiver_id'),str):fields['receiver_id']=args['receiver_id']
                if isinstance(args.get('message'),str):fields['content']=args['message']
                update('message',identifier,fields);accept();return effect
        if method=='delete_message' and out.get('deleted_status') is True and isinstance(out.get('receiver_id'),str):
            effect['operation']={'kind':'delete_latest_message','receiver_id':out['receiver_id']}
            observe('message_deleted_without_identity',{'receiver_id':out['receiver_id']})
            accept(coverage='observation_only');return effect
        for name,key in [('list_users','user_list'),('view_messages_sent','messages'),('search_messages','results'),('get_message_stats','stats')]:
            if method==name and key in out:
                observe(name+'_snapshot',out[key]);accept(coverage='observation_only');return effect

    if domain=='TicketAPI':
        fields={'id','title','description','status','priority','created_by','resolution'}
        if method in ('create_ticket','get_ticket') and type(out.get('id')) in (str,int):
            update('ticket',out['id'],{**{k:v for k,v in out.items() if k in fields},'exists':True});accept();return effect
        if method=='get_user_tickets' and isinstance(output,list) and all(isinstance(row,dict) and type(row.get('id')) in (str,int) for row in output):
            for row in output:update('ticket',row['id'],{**{k:v for k,v in row.items() if k in fields},'exists':True})
            observe('returned_ticket_ids',[row['id'] for row in output]);accept();return effect
        identity=args.get('ticket_id')
        if type(identity) in (str,int):
            success_strings={'close_ticket':f'Ticket {identity} has been closed successfully.',
                             'resolve_ticket':f'Ticket {identity} has been resolved successfully.',
                             'edit_ticket':f'Ticket {identity} has been updated successfully.'}
            if method in success_strings and out.get('status')==success_strings[method]:
                values=({'status':'Closed'} if method=='close_ticket' else
                        {'status':'Resolved', 'resolution':args.get('resolution')} if method=='resolve_ticket' else
                        {k:v for k,v in (args.get('updates') if isinstance(args.get('updates'),dict) else {}).items() if k in {'title','description','status','priority'} and v is not None})
                update('ticket',identity,values);accept();return effect

    # Known domain, unrecognized result or unsupported mutation: never clear other domains.
    if effect['footprint'] in ('write','unknown'):
        invalidate(reason='unmodeled_domain_mutation')
    return effect
