"""Pure graph-layout primitives; file loaders and campaign execution removed."""
from collections import Counter, defaultdict
import hashlib, itertools, json

def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def exchange_partition(events, order):
    """Require one complete contiguous native call group; never cut parallel results.

    Unsafe exchange spans make BOTH branches chronological. Text-adjacent groups
    become fixed context components; no semantic attachment guess is made.
    """
    groups = defaultdict(list)
    group_for = {}
    calls = {i: events[i] for i in order if events[i]['category'] == 'tool_call'}
    for i in order:
        n = events[i]
        if n['category'] == 'tool_call':
            g = n['call_group']
        elif n['category'] == 'tool_result':
            require(n['result_of'] in calls, 'Orphan result')
            g = calls[n['result_of']]['call_group']
        else:
            continue
        groups[g].append(i)
        group_for[i] = g
    reasons = []
    positions = {i: j for j, i in enumerate(order)}
    for g, ids in groups.items():
        call_ids = [i for i in ids if i in calls]
        result_targets = [events[i]['result_of'] for i in ids if events[i]['category'] == 'tool_result']
        require(Counter(call_ids) == Counter(result_targets), 'Incomplete or repeated call results')
        locs = [positions[i] for i in ids]
        if locs != list(range(min(locs), max(locs) + 1)):
            reasons.append('noncontiguous_exchange:' + g)
        if len({events[i]['episode'] for i in ids}) != 1:
            reasons.append('cross_episode_exchange:' + g)
    episodes = []
    for i in order:
        ep = events[i]['episode']
        if not episodes or episodes[-1] != ep:
            require(ep not in episodes, 'Noncontiguous source episode')
            episodes.append(ep)
    for ep in episodes:
        ids = [i for i in order if events[i]['episode'] == ep]
        require(events[ids[0]]['category'] == 'user_request', 'Episode does not start with user')
    if reasons:
        return {'safe': False, 'reasons': reasons, 'groups': dict(groups), 'group_for': group_for,
                'episodes': episodes, 'components': []}
    units = []
    seen = set()
    for i in order:
        g = group_for.get(i)
        if g is not None:
            if g not in seen:
                units.append({'ids': groups[g], 'exchange': g})
                seen.add(g)
        else:
            units.append({'ids': [i], 'exchange': None})
    parent = list(range(len(units)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i

    def union(i, j):
        parent[find(j)] = find(i)

    for j, u in enumerate(units):
        if any(events[i]['category'] == 'assistant_statement' for i in u['ids']):
            for k in (j - 1, j + 1):
                if not 0 <= k < len(units):
                    continue
                other = units[k]
                same_episode = events[u['ids'][0]]['episode'] == events[other['ids'][0]]['episode']
                is_exchange_or_assistant = (other['exchange'] is not None or
                    all(events[i]['category'] == 'assistant_statement' for i in other['ids']))
                if same_episode and is_exchange_or_assistant:
                    union(j, k)
    components = []
    for j, unit in enumerate(units):
        root = find(j)
        if not components or components[-1]['root'] != root:
            components.append({'root': root, 'ids': [], 'groups': []})
        components[-1]['ids'].extend(unit['ids'])
        if unit['exchange'] is not None:
            components[-1]['groups'].append(unit['exchange'])
    for component in components:
        component.pop('root')
        component['fixed'] = any(i not in group_for for i in component['ids'])
        require(component['fixed'] or len(component['groups']) == 1, 'Unexpected pure compound')
    require([i for c in components for i in c['ids']] == order, 'Noncontiguous context component')
    return {'safe': True, 'reasons': [], 'groups': dict(groups), 'group_for': group_for,
            'episodes': episodes, 'components': components}

def membership_events(graph):
    nodes = {n['id']: n for n in graph['record_layer']['nodes']}
    out = defaultdict(set)
    for edge in graph['record_layer']['edges']:
        require(edge['relation'] == 'same_typed_identifier_member', 'Unexpected evidence graph edge')
        occurrence = nodes[edge['from']]
        out[edge['to']].add(nodes[occurrence['record']]['event_id'])
    return dict(out)

def reach(seeds, partition, anchors):
    groups = partition['groups']
    valid = (type(seeds) is list and len(seeds) <= 2 and
             all(type(s) is str for s in seeds) and len(set(seeds)) == len(seeds) and
             all(s in groups for s in seeds))
    if not valid:
        return {'valid': False, 'reason': 'invalid_seed_set', 'S': set(), 'G': set(), 'anchors': []}
    initial = {i for g in seeds for i in groups[g]}
    # This is the ONLY traversal start: display closures and new owners never fan out.
    touched = sorted(a for a, ids in anchors.items() if initial & ids)
    reached_events = {i for a in touched for i in anchors[a]}
    require(all(i in partition['group_for'] for i in reached_events), 'Membership outside exchange')
    expanded = set(seeds) | {partition['group_for'][i] for i in reached_events}
    return {'valid': True, 'reason': None, 'S': set(seeds), 'G': expanded, 'anchors': touched}

def barrier_order(partition, selected):
    result, pending = [], []

    def flush():
        result.extend(c for c in pending if c['groups'][0] in selected)
        result.extend(c for c in pending if c['groups'][0] not in selected)
        pending.clear()
    for c in partition['components']:
        if c['fixed']:
            flush()
            result.append(c)
        else:
            pending.append(c)
    flush()
    return [i for c in result for i in c['ids']]

def episode_selection(partition, events, selected):
    return {events[partition['groups'][g][0]]['episode'] for g in selected}

def episode_order(partition, events, order, selected):
    episodes = episode_selection(partition, events, selected)
    arrangement = ([ep for ep in partition['episodes'] if ep in episodes] +
                   [ep for ep in partition['episodes'] if ep not in episodes])
    return [i for ep in arrangement for i in order if events[i]['episode'] == ep]

def typed_event_chunks(evidence, e):
    """Slice by typed segment contract, never search untrusted source text."""
    segments = e.render_evidence_segments(evidence)
    nodes = {n['id']: n for n in evidence['evidence_view']['nodes']}
    chunks, cursor, previous = {}, 1, None
    for i in evidence['evidence_view']['recorded_order']:
        n = nodes[i]
        start = cursor
        if n['episode'] != previous:
            require(segments[cursor] == {'kind': 'label', 'text': 'EPISODE ' + n['episode'] + '\n'},
                    'Episode segment contract')
            cursor += 1
        require(segments[cursor]['kind'] == 'label', 'Event label contract')
        cursor += 1
        for field in n['fields']:
            require(segments[cursor]['kind'] == segments[cursor + 2]['kind'] == 'label', 'Field fence contract')
            value = segments[cursor + 1]
            require(value['kind'] == 'evidence' and value['node_id'] == i and
                    value['field'] == field['field'] and value['value_type'] == field['value_type'], 'Field owner contract')
            cursor += 3
        chunks[i] = segments[start:cursor]
        previous = n['episode']
    return segments[:1], chunks, segments[cursor:]

def prepare(graph, core):
    e, o, p, r, v = core
    require(r.audit_record_graph(graph)['ok'], 'Invalid evidence graph source')
    evidence = o.strip_observed_graph(p.restore_observed_graph(r.strip_record_graph(graph)))
    e.audit_evidence_graph(evidence)
    require(evidence['evidence_view']['fact_order'] == [], 'Only episodic evidence supported')
    order = evidence['evidence_view']['recorded_order']
    all_nodes = {n['id']: n for n in evidence['evidence_view']['nodes']}
    events = {i: all_nodes[i] for i in order}
    partition = exchange_partition(events, order)
    head, chunks, tail = typed_event_chunks(evidence, e)
    frozen = v.render_record_view_segments(graph, view='full', visible_observations=False)
    require(''.join(s['text'] for s in head + [s for i in order for s in chunks[i]] + tail) == frozen[0]['text'],
            'Chronological evidence differs from frozen O-off body')
    tail += frozen[1:]
    directory = [{'episode': ep, 'first_original_ordinal': min(events[i]['ordinal'] for i in order if events[i]['episode'] == ep),
                  'last_original_ordinal': max(events[i]['ordinal'] for i in order if events[i]['episode'] == ep)}
                 for ep in partition['episodes']]
    index = {'kind': 'chronology_index', 'text': 'ORIGINAL_EPISODE_ORDER\n' +
             ''.join(f"{d['episode']} original_order={d['first_original_ordinal']}..{d['last_original_ordinal']}\n" for d in directory)}
    return {'graph_sha256': sha(canon(graph)), 'events': events, 'order': order, 'partition': partition,
            'anchors': membership_events(graph), 'head': head, 'chunks': chunks, 'tail': tail,
            'index': index, 'directory': directory,
            'record_nodes': [n for n in graph['record_layer']['nodes'] if n['category'] == 'payload_record'],
            'payload_spans': {n['id']: n['span'] for n in graph['payload_layer']['nodes']},
            'frozen_full_body_sha256': sha(''.join(s['text'] for s in frozen).encode())}

def segment_list(prepared, branch, order):
    require(branch in ('barrier', 'whole_episode'), 'Unknown branch')
    return prepared['head'] + ([prepared['index']] if branch == 'whole_episode' else []) + [
        s for i in order for s in prepared['chunks'][i]] + prepared['tail']

def audit_layout(prepared, branch, order, segments):
    original, events, part = prepared['order'], prepared['events'], prepared['partition']
    reference = segment_list(prepared, branch, original)
    evidence = [s for s in segments if s['kind'] == 'evidence']
    original_evidence = [s for s in reference if s['kind'] == 'evidence']
    owners = [(s['node_id'], s['field']) for s in evidence]
    checks = {
        'typed_segments_match_declared_event_order': canon(segments) == canon(segment_list(prepared, branch, order)),
        'event_owners_exactly_once': Counter(order) == Counter(original) and len(order) == len(set(order)),
        'field_owners_exactly_once': len(owners) == len(set(owners)) and Counter(owners) == Counter((s['node_id'], s['field']) for s in original_evidence),
        'typed_evidence_segments_exact': Counter(canon(s) for s in evidence) == Counter(canon(s) for s in original_evidence),
        'metadata_segment_multiset_exact': Counter(canon(s) for s in segments if s['kind'] != 'evidence') == Counter(canon(s) for s in reference if s['kind'] != 'evidence'),
        'all_segment_multiset_exact': Counter(canon(s) for s in segments) == Counter(canon(s) for s in reference),
        'source_event_blocks_exact': all([s for s in segments if s.get('node_id') == i] == [s for s in reference if s.get('node_id') == i] for i in original),
    }
    pos = {i: j for j, i in enumerate(order)}
    source_pos = {i: j for j, i in enumerate(original)}
    if part['safe']:
        checks['complete_exchange_order_and_adjacency'] = all(
            [pos[i] for i in ids] == list(range(pos[ids[0]], pos[ids[0]] + len(ids))) for ids in part['groups'].values())
    else:
        checks['unsafe_partition_full_chronological_fallback'] = order == original
    if branch == 'barrier':
        checks['fixed_context_components_positions_exact'] = all(
            all(pos[i] == source_pos[i] for i in c['ids']) for c in part['components'] if c['fixed'])
        checks['episode_order_unchanged'] = [events[i]['episode'] for i in order] == [events[i]['episode'] for i in original]
    else:
        checks['whole_episode_internal_order_and_adjacency'] = all(
            [pos[i] for i in original if events[i]['episode'] == ep] ==
            list(range(min(pos[i] for i in original if events[i]['episode'] == ep),
                       max(pos[i] for i in original if events[i]['episode'] == ep) + 1)) for ep in part['episodes'])
    inversions = [[a, b] for j, a in enumerate(original) for b in original[j + 1:] if pos[a] > pos[b]]
    reversed_precedes = [[a, b] for a, b in zip(original, original[1:]) if pos[a] > pos[b]]
    body = ''.join(s['text'] for s in segments).encode()
    return {'body_sha256': sha(body), 'body_utf8_bytes': len(body), 'body_characters': len(body.decode()),
            'event_owner_order': order, 'field_owner_order': [list(x) for x in owners],
            'g9_record_owner_order': [n['id'] for n in sorted(prepared['record_nodes'], key=lambda n: (pos[n['event_id']], n['field'], prepared['payload_spans'][n['payload_node']], n['id']))],
            'checks': checks, 'all_checks_passed': all(checks.values()),
            'field_evidence_multiset_sha256': sha(canon(sorted(sha(canon(s)) for s in evidence))),
            'metadata_multiset_sha256': sha(canon(sorted(sha(canon(s)) for s in segments if s['kind'] != 'evidence'))),
            'ordinal_inversion_pairs': inversions, 'ordinal_inversion_count': len(inversions),
            'cross_episode_inversion_count': sum(events[a]['episode'] != events[b]['episode'] for a, b in inversions),
            'reversed_original_precedes': reversed_precedes,
            'moved_event_count': sum(pos[i] != source_pos[i] for i in original),
            'total_absolute_event_displacement': sum(abs(pos[i] - source_pos[i]) for i in original)}

def variants(prepared, branch, seeds):
    part, events = prepared['partition'], prepared['events']
    selected = reach(seeds, part, prepared['anchors'])
    fallback = not part['safe'] or not selected['valid']
    orders = {'C': prepared['order']}
    for arm in ('S', 'G'):
        orders[arm] = (prepared['order'] if fallback else
            barrier_order(part, selected[arm]) if branch == 'barrier' else
            episode_order(part, events, prepared['order'], selected[arm]))
    s_ep = episode_selection(part, events, selected['S'])
    g_ep = episode_selection(part, events, selected['G'])
    s_display = {g for g, ids in part['groups'].items() if events[ids[0]]['episode'] in s_ep}
    g_display = {g for g, ids in part['groups'].items() if events[ids[0]]['episode'] in g_ep}
    delta = selected['G'] - selected['S']
    info = {'seeds': seeds, 'valid': selected['valid'], 'fallback': fallback,
            'fallback_reasons': part['reasons'] + ([selected['reason']] if selected['reason'] else []),
            'initial_exchange_groups': sorted(selected['S']), 'expanded_exchange_groups': sorted(selected['G']),
            'g_only_exchange_groups': sorted(delta), 'touched_anchors': selected['anchors'],
            'S_selected_episodes': sorted(s_ep), 'G_selected_episodes': sorted(g_ep),
            'episode_display_S_added_groups': sorted(s_display - selected['S']),
            'episode_display_G_added_groups': sorted(g_display - selected['G']),
            'g_increment_swallowed_by_S_episode_display': sorted(delta & s_display),
            'new_G_display_episodes': sorted(g_ep - s_ep),
            'S_differs_C': orders['S'] != orders['C'], 'G_differs_C': orders['G'] != orders['C'],
            'G_differs_S': orders['G'] != orders['S'],
            'G_minus_S_owner_position_changes': [i for i in prepared['order'] if orders['G'].index(i) != orders['S'].index(i)]}
    return info, orders

