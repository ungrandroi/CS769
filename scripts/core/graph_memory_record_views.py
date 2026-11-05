"""Offline B/N/F displays of one complete G9 graph; no paid profile is chosen.

base hides the record appendix; nodes hides only its explicit memberships;
full delegates to the frozen visibility renderer. Stored edges never change.
Carrier, CLI, scheduler, official tools and evaluation are outside this module.
"""
from core.graph_memory_records import audit_record_graph
from core.graph_memory_record_visibility import render_record_visibility_segments

VIEWS = ('base', 'nodes', 'full')
LAYOUT = 'same-graph-record-views-v1'


def _require_full_graph(graph, view, visible_observations):
    if view not in VIEWS:
        raise ValueError('Unknown record display view')
    if type(visible_observations) is not bool:
        raise ValueError('visible_observations must be a boolean')
    audit = audit_record_graph(graph)
    if not audit['ok']:
        raise ValueError('Invalid record graph: ' + '; '.join(audit['errors']))
    if graph['record_layer']['variant'] != 'record-joins-v1':
        raise ValueError('Display ablation requires the complete record-joins-v1 graph')
    return audit


def _without_displayed_memberships(graph, appendix):
    """Verify and replace only the graph-derived tail of a typed appendix.

    The frozen renderer ends that segment with one line per anchor. Exact lines
    are recomputed from the full graph before replacement; no raw evidence or
    marker-shaped source string is scanned or removed. Nodes/edges stay intact.
    """
    layer = graph['record_layer']
    occurrences = [n for n in layer['nodes'] if n['category'] == 'identifier_occurrence']
    anchors = [n for n in layer['nodes'] if n['category'] == 'identifier_anchor']
    aliases = {n['id']: 'o' + str(i) for i, n in enumerate(occurrences)}
    complete, bare = [], []
    for i, anchor in enumerate(anchors):
        label = 'j' + str(i) + ' ' + anchor['namespace'] + ' (' + anchor['value_type'] + ')'
        members = [aliases[e['from']] for e in layer['edges'] if e['to'] == anchor['id']]
        if not members:
            raise ValueError('Complete graph anchor lacks memberships')
        complete.append(label + ': ' + ' '.join(members))
        bare.append(label)
    parts = appendix['text'].rsplit('\n', len(anchors))
    if not anchors or len(parts) != len(anchors) + 1 or parts[1:] != complete:
        raise ValueError('Frozen external appendix anchor-tail contract changed')
    return {**appendix, 'text': '\n'.join([parts[0], *bare])}


def render_record_view_segments(graph, *, view='full', visible_observations=True):
    audit = _require_full_graph(graph, view, visible_observations)
    segments = render_record_visibility_segments(graph, visible_observations=visible_observations)
    body_kind = 'g7-compatible' if visible_observations else 'g5-compatible'
    if ([s['kind'] for s in segments] != [body_kind] +
            (['g9_external_references'] if audit['active'] else [])):
        raise ValueError('Frozen visibility renderer segment contract changed')
    if view == 'base' or not audit['active']:
        return segments[:1]
    if view == 'nodes':
        return [segments[0], _without_displayed_memberships(graph, segments[1])]
    return segments


def render_record_view_graph(graph, *, view='full', visible_observations=True):
    return ''.join(s['text'] for s in render_record_view_segments(
        graph, view=view, visible_observations=visible_observations))


def audit_record_view_render(graph, *, view='full', visible_observations=True, rendered_text=None):
    audit = audit_record_graph(graph)
    result = {**audit, 'layout': LAYOUT, 'view': view, 'visible_observations': visible_observations,
        'stored_edge_count': audit['edge_count'], 'displayed_edge_count': 0,
        'displayed_locator_count': 0, 'displayed_anchor_count': 0,
        'characters': 0, 'base_characters': 0, 'appendix_characters': 0, 'exact_base': False}
    try:
        segments = render_record_view_segments(graph, view=view, visible_observations=visible_observations)
        text = ''.join(s['text'] for s in segments)
        if rendered_text is not None and rendered_text != text:
            raise ValueError('Supplied rendering differs from the same-graph display view')
        result.update(displayed_edge_count=audit['edge_count'] if view == 'full' else 0,
            displayed_locator_count=(audit['record_count'] + audit['occurrence_count']) if view != 'base' else 0,
            displayed_anchor_count=audit['anchor_count'] if view != 'base' else 0,
            characters=len(text), base_characters=len(segments[0]['text']),
            appendix_characters=len(text) - len(segments[0]['text']), exact_base=len(segments) == 1)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result['ok'] = False
        result['errors'] = [str(exc)]
    return result
