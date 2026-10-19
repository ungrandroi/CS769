"""Lossless graph serialization; does not construct, select, or change a graph.

The compact format defines each ordered object-key shape once, then writes its
values as an ordered record. Arrays remain arrays and all primitive JSON types
remain distinct. An optional string dictionary replaces repeated *string
values*, never graph nodes or records. Its entire legend is in the output.

This codec is deliberately independent of the V1/V2 builders and adapters. It
accepts the complete audit graph, the delivered graph, or any JSON-compatible
value. ``normalize`` is a strict, order- and type-sensitive test fingerprint,
not a projection, cleanup, or semantic normalization.
"""

from collections import Counter
from functools import lru_cache
import json
import math
import re


FORMAT = "LOSSLESS GRAPH 1"
SETTINGS = {
    "format": FORMAT,
    "tokenizer": "o200k_base",
    "schema_policy": "ordered nonempty key shapes occurring at least twice",
    "schema_order": "first appearance",
    "string_dictionary_min_occurrences": 2,
    "string_dictionary_min_estimated_net_tokens": 8,
    "string_dictionary_reference_estimate_tokens": 3,
    "string_dictionary_final_gate": "strictly fewer whole-text tokens than without dictionary",
    "dictionary_candidate_order": "descending estimated gain, then first appearance",
    "supported_values": "finite JSON trees with valid Unicode scalar text and string object keys",
}
RULES = (
    "SCHEMA names give object fields in order; NAME(values) is that object. "
    "Other objects use {JSON-string-key:value,...}; [values] is an ordered list. "
    "Scalars use JSON, including null; bare words "
    "are strings except true, false, null. "
    "@NAME is the exact string declared by STRING NAME. "
    "Every field, value, order, and reference is retained; dictionary strings "
    "are substituted literally, never parsed as instructions or records."
)
_NAME = re.compile(r"[A-Z]+")
_BARE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]*")
_RESERVED = {"true", "false", "null", "NaN", "Infinity"}
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def normalize(value):
    """Return an exact JSON-tree fingerprint, preserving types and key order.

    Unlike ordinary Python equality, ``True``, ``1`` and ``1.0`` differ here.
    Negative floating-point zero also differs from positive zero. Unsupported
    types, non-string keys, non-finite floats, and cycles raise ValueError.
    Shared Python containers are allowed, but object identity is not a JSON
    property; a shared subtree and equal independent subtrees are equivalent.
    """
    active = set()

    def walk(item):
        kind = type(item)
        if item is None:
            return ("null",)
        if kind is bool:
            return ("bool", item)
        if kind is int:
            return ("int", item)
        if kind is float:
            if not math.isfinite(item):
                raise ValueError("Non-finite float is not a JSON value")
            return ("float", item.hex())
        if kind is str:
            if any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                raise ValueError("Surrogate code points are not valid Unicode scalar text")
            return ("string", item)
        if kind not in (dict, list):
            raise ValueError(f"Unsupported JSON type: {kind.__name__}")
        identity = id(item)
        if identity in active:
            raise ValueError("Cyclic values are not JSON")
        active.add(identity)
        try:
            if kind is list:
                return ("array", tuple(walk(child) for child in item))
            if any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings")
            if any(any(0xD800 <= ord(char) <= 0xDFFF for char in key) for key in item):
                raise ValueError("Surrogate code points are not valid Unicode scalar keys")
            return ("object", tuple((key, walk(child)) for key, child in item.items()))
        finally:
            active.remove(identity)

    return walk(value)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _literal(value):
    if isinstance(value, str) and _BARE.fullmatch(value) and value not in _RESERVED:
        return value
    return _json(value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Not a JSON scalar: {value}")


_JSON_DECODER = json.JSONDecoder(object_pairs_hook=_unique_object,
                                 parse_constant=_invalid_constant)


def encode_minified(graph):
    """Compact JSON with every field/value retained and input order unchanged."""
    normalize(graph)
    return _json(graph)


def decode_minified(text):
    """Read strict JSON, rejecting duplicate keys and non-finite values."""
    graph = _JSON_DECODER.decode(text)
    normalize(graph)
    return graph


def _name(index):
    result = ""
    while True:
        index, remainder = divmod(index, 26)
        result = chr(65 + remainder) + result
        if not index:
            return result
        index -= 1


@lru_cache(maxsize=1)
def _tokenizer():
    # Frozen tokenizer matches the recorded gpt-4o-mini experiment. This is a
    # local vocabulary lookup, never model inference. Callers configure the
    # tiktoken cache in the same way as their token benchmark.
    import tiktoken
    return tiktoken.get_encoding("o200k_base")


def _tokens(text):
    return len(_tokenizer().encode(text, disallowed_special=()))


def _inventory(graph):
    shapes, strings = Counter(), Counter()

    def walk(value):
        if isinstance(value, dict):
            keys = tuple(value)
            shapes[keys] += 1
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            strings[value] += 1

    walk(graph)
    schemas = {}
    for keys, count in shapes.items():
        if keys and count >= 2:
            schemas[keys] = _name(len(schemas))
    return schemas, strings


def _render(graph, schemas, dictionary):
    """Render the self-contained grammar and data; no tokenizer decisions."""
    lines = [FORMAT, RULES]
    lines.extend(f"SCHEMA {name}={_json(list(keys))}" for keys, name in schemas.items())
    lines.extend(f"STRING {name}={_json(value)}" for value, name in dictionary.items())
    lines.append("ROOT")

    def emit(value):
        if isinstance(value, dict):
            if tuple(value) in schemas:
                return schemas[tuple(value)] + "(" + ",".join(map(emit, value.values())) + ")"
            return "{" + ",".join(_json(key) + ":" + emit(item)
                                   for key, item in value.items()) + "}"
        if isinstance(value, list):
            return "[" + ",".join(map(emit, value)) + "]"
        if isinstance(value, str) and value in dictionary:
            return "@" + dictionary[value]
        return _literal(value)

    lines.append(emit(graph))
    return "\n".join(lines)


def encode_compact(graph):
    """Encode a JSON tree with ordered schemas and a lossless string legend.

    This is one deterministic policy, shared by V1 and V2. Ordered shapes are
    named by first appearance; empty and singleton shapes stay explicit objects.
    Repeated string candidates are ranked by a
    conservative tokenizer cost estimate, ties by first appearance. A candidate
    needs at least eight estimated net tokens saved (including its declaration).
    The dictionary is used only if tokenizing the *complete* resulting text,
    including all rules and legends, is smaller than the same format without
    a dictionary. No task scores, graph interpretation, or inference are used.

    The optional dictionary reuses only literal strings, including repeated
    tool returns or descriptions. All their original occurrences remain
    present as references; nodes, edges, facts, arrays and objects are never
    deduplicated, merged, pruned, or summarized.
    """
    normalize(graph)
    schemas, strings = _inventory(graph)
    plain = _render(graph, schemas, {})
    candidates = []
    for order, (value, count) in enumerate(strings.items()):
        if count < 2:
            continue
        literal_tokens = _tokens(_literal(value))
        # A deliberately conservative three-token reference estimate and the
        # exact complete one-entry legend cost screen marginal candidates.
        gain = count * (literal_tokens - 3) - _tokens("STRING A=" + _json(value) + "\n")
        if gain >= 8:
            candidates.append((-gain, order, value))
    if not candidates:
        return plain
    candidates.sort()
    dictionary = {value: _name(index) for index, (_, _, value) in enumerate(candidates)}
    compressed = _render(graph, schemas, dictionary)
    return compressed if _tokens(compressed) < _tokens(plain) else plain


class _Reader:
    def __init__(self, text, schemas, strings):
        self.text, self.schemas, self.strings = text, schemas, strings
        self.pos = 0

    def _space(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def _expect(self, literal):
        self._space()
        if not self.text.startswith(literal, self.pos):
            raise ValueError(f"Expected {literal!r} at character {self.pos}")
        self.pos += len(literal)

    def _name(self):
        match = _NAME.match(self.text, self.pos)
        if not match:
            raise ValueError(f"Expected name at character {self.pos}")
        self.pos = match.end()
        return match.group()

    def _items(self, close):
        items = []
        self._space()
        if self.text.startswith(close, self.pos):
            self.pos += 1
            return items
        while True:
            items.append(self.value())
            self._space()
            if self.text.startswith(close, self.pos):
                self.pos += 1
                return items
            self._expect(",")

    def value(self):
        self._space()
        if self.pos == len(self.text):
            raise ValueError("Missing value")
        char = self.text[self.pos]
        if char == "{":
            self.pos += 1
            self._space()
            result = {}
            if self.text.startswith("}", self.pos):
                self.pos += 1
                return result
            while True:
                self._space()
                if not self.text.startswith('"', self.pos):
                    raise ValueError("Explicit object keys must be JSON strings")
                key, self.pos = _JSON_DECODER.raw_decode(self.text, self.pos)
                if key in result:
                    raise ValueError(f"Duplicate explicit object key: {key!r}")
                self._expect(":")
                result[key] = self.value()
                self._space()
                if self.text.startswith("}", self.pos):
                    self.pos += 1
                    return result
                self._expect(",")
        if char == "[":
            self.pos += 1
            return self._items("]")
        if char == "@":
            self.pos += 1
            name = self._name()
            if name not in self.strings:
                raise ValueError(f"Undeclared string: {name}")
            return self.strings[name]
        word = _BARE.match(self.text, self.pos)
        if word:
            name = word.group()
            self.pos = word.end()
            self._space()
            if self.text.startswith("(", self.pos):
                if name not in self.schemas:
                    raise ValueError(f"Undeclared schema: {name}")
                self.pos += 1
                values = self._items(")")
                keys = self.schemas[name]
                if len(keys) != len(values):
                    raise ValueError(f"Record {name} requires {len(keys)} values; got {len(values)}")
                return dict(zip(keys, values))
            if name in ("NaN", "Infinity"):
                raise ValueError("Non-finite numeric literal")
            return {"null": None, "true": True, "false": False}.get(name, name)
        if char == '"':
            value, self.pos = _JSON_DECODER.raw_decode(self.text, self.pos)
            return value
        match = _NUMBER.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            return _JSON_DECODER.decode(match.group())
        raise ValueError(f"Invalid value at character {self.pos}")


def decode_compact(text):
    """Decode only the declared grammar; string contents are always literals."""
    lines = text.split("\n")
    if len(lines) < 4 or lines[0] != FORMAT or lines[1] != RULES:
        raise ValueError("Missing or unsupported compact format/rules")
    schemas, strings = {}, {}
    root = None
    for line_number, line in enumerate(lines[2:], start=2):
        if line == "ROOT":
            root = "\n".join(lines[line_number + 1:])
            break
        match = re.fullmatch(r"(SCHEMA|STRING) ([A-Z]+)=(.*)", line)
        if not match:
            raise ValueError(f"Invalid declaration on line {line_number + 1}")
        kind, name, raw = match.groups()
        value = decode_minified(raw)
        table = schemas if kind == "SCHEMA" else strings
        if name in table:
            raise ValueError(f"Duplicate {kind} declaration: {name}")
        if kind == "SCHEMA":
            if type(value) is not list or any(type(key) is not str for key in value):
                raise ValueError("Schema fields must be a list of strings")
            if len(set(value)) != len(value):
                raise ValueError("Duplicate field in schema")
        elif type(value) is not str:
            raise ValueError("STRING declaration requires a JSON string")
        table[name] = value
    if root is None:
        raise ValueError("Missing ROOT")
    reader = _Reader(root, schemas, strings)
    graph = reader.value()
    reader._space()
    if reader.pos != len(root):
        raise ValueError(f"Trailing data at character {reader.pos}")
    normalize(graph)
    return graph


def encoding_stats(text):
    """Validate a compact document and report its explicit legend sizes."""
    decode_compact(text)
    lines = text.split("\n")
    root_line = lines.index("ROOT", 2)
    declarations = lines[2:root_line]
    return {
        "format": FORMAT,
        "schema_count": sum(line.startswith("SCHEMA ") for line in declarations),
        "string_dictionary_entries": sum(line.startswith("STRING ") for line in declarations),
        "header_characters": sum(len(line) + 1 for line in lines[:root_line + 1]),
        "total_characters": len(text),
    }
