"""Render the same G9 graph with optional display of derived G7 observations.

All original visible evidence is restored from the owned payload graph. Hiding
the derived observation appendix does not delete graph nodes or source fields.
Carrier roles are an adapter concern and never enter this renderer.
"""
from core.graph_memory_evidence import render_evidence_graph
from core.graph_memory_observed import strip_observed_graph
from core.graph_memory_payload import restore_observed_graph
from core.graph_memory_records import strip_record_graph, audit_record_graph
from core.graph_memory_record_render import (
    render_external_record_segments, audit_external_record_render)

EVIDENCE_LAYOUT = 'external-record-evidence-v1'


def render_record_visibility_segments(graph, *, visible_observations=True):
    if type(visible_observations) is not bool:
        raise ValueError('visible_observations must be a boolean')
    # The existing renderer validates the exact G9 graph and computes locators.
    external = render_external_record_segments(graph)
    if visible_observations:
        return external
    observed = restore_observed_graph(strip_record_graph(graph))
    evidence = strip_observed_graph(observed)
    body = render_evidence_graph(evidence, layout='chronological-first')
    # Select typed segments; never erase marker-shaped source text.
    appendix = [segment for segment in external if segment['kind'] == 'g9_external_references']
    return [{'kind': 'g5-compatible', 'text': body}, *appendix]


def render_record_visibility_graph(graph, *, visible_observations=True):
    return ''.join(segment['text'] for segment in render_record_visibility_segments(
        graph, visible_observations=visible_observations))


def audit_record_visibility_render(graph, *, visible_observations=True, rendered_text=None):
    if type(visible_observations) is not bool:
        raise ValueError('visible_observations must be a boolean')
    if visible_observations:
        return audit_external_record_render(graph, rendered_text=rendered_text)
    audit = audit_record_graph(graph)
    result = {**audit, 'layout': EVIDENCE_LAYOUT, 'visible_observations': False,
              'characters': 0, 'base_characters': 0, 'record_appendix_characters': 0,
              'exact_g5': False}
    if not audit['ok']:
        return result
    try:
        segments = render_record_visibility_segments(graph, visible_observations=False)
        body = segments[0]['text']
        text = ''.join(segment['text'] for segment in segments)
        if rendered_text is not None and rendered_text != text:
            raise ValueError('Supplied rendering differs from the evidence-only display layout')
        result.update(characters=len(text), base_characters=len(body),
                      record_appendix_characters=len(text)-len(body), exact_g5=text == body)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
        result['ok'] = False
        result['errors'] = [str(exc)]
    return result
