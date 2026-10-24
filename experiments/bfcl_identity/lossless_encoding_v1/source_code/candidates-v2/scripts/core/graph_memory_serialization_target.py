"""Compact graph encoding with an explicit target-model token counter.

Reuses the shared lossless grammar, inventory and renderer. No default GPT
counter, tokenizer download, or model inference is used.
"""

from typing import Callable

from core.graph_memory_serialization import (
    SETTINGS as _FROZEN_SETTINGS,
    _inventory,
    _json,
    _literal,
    _name,
    _render,
    normalize,
)


SETTINGS = {
    **_FROZEN_SETTINGS,
    "tokenizer": "caller_supplied_count_tokens",
    "selection_version": "injected-target-counter-1",
    "grammar_provenance": "graph_memory_serialization.py:LOSSLESS GRAPH 1",
    "same_codec_grammar": True,
    "selection_tokenizer_is_injected": True,
    "target_tokenizer_provenance_required": True,
}


def encode_compact(graph, count_tokens: Callable[[str], int]) -> str:
    """Encode with the frozen policy, using only ``count_tokens`` for costs.

    ``count_tokens(text)`` must deterministically return a non-negative integer
    count for the supplied text. A bound ``LocalQwenTokenizer.count`` method is
    suitable. Count without conversational wrappers or special-token insertion;
    request/template token overhead belongs in the benchmark's separate metric.

    All original occurrences remain present. Only repeated literal strings can
    become dictionary references, and the full encoded document (including its
    schema/rules/string legends) must be strictly smaller than the same document
    without a dictionary. Changing this counter never changes the decoder or
    stored graph data.
    """
    if not callable(count_tokens):
        raise TypeError("count_tokens must be callable")

    def tokens(text):
        count = count_tokens(text)
        if type(count) is not int or count < 0:
            raise ValueError("count_tokens must return a non-negative integer")
        return count

    normalize(graph)
    schemas, strings = _inventory(graph)
    plain = _render(graph, schemas, {})
    candidates = []
    for order, (value, count) in enumerate(strings.items()):
        if count < SETTINGS["string_dictionary_min_occurrences"]:
            continue
        literal_tokens = tokens(_literal(value))
        gain = (
            count * (literal_tokens - SETTINGS["string_dictionary_reference_estimate_tokens"])
            - tokens("STRING A=" + _json(value) + "\n")
        )
        if gain >= SETTINGS["string_dictionary_min_estimated_net_tokens"]:
            candidates.append((-gain, order, value))
    if not candidates:
        return plain
    candidates.sort()
    dictionary = {value: _name(index) for index, (_, _, value) in enumerate(candidates)}
    compressed = _render(graph, schemas, dictionary)
    return compressed if tokens(compressed) < tokens(plain) else plain
