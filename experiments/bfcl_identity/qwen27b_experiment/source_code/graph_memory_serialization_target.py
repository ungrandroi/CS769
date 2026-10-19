"""Target-tokenizer selection for the frozen, lossless compact graph grammar.

Only token-cost decisions are delegated to the supplied counter. The original
``graph_memory_serialization.py`` remains unchanged, and all value handling,
schema inventory, rendering, and decoding are reused directly from that file.
No tokenizer is downloaded or looked up here, and no inference is performed.

Provenance must record this module and the caller's tokenizer identity: the
grammar and candidate policy are unchanged, but a different tokenizer can
select a different literal-string dictionary. Prior o200k results are not
measurements for another model or tokenizer.
"""

from typing import Callable

from graph_memory_serialization import (
    FORMAT,
    RULES,
    SETTINGS as _FROZEN_SETTINGS,
    _inventory,
    _json,
    _literal,
    _name,
    _render,
    decode_compact,
    decode_minified,
    encode_minified,
    encoding_stats,
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
    stored graph data, and never mutates the frozen codec's tokenizer globals.
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
