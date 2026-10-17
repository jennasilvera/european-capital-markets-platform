"""Closed tagged codec; bounds apply to both retained and imported content."""

import json
import re
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from decimal import MAX_EMAX, MIN_ETINY, Decimal, DecimalException
from enum import Enum
from types import UnionType
from typing import TypeAliasType, Union, get_args, get_origin, get_type_hints

from european_capital_markets.analytics._bundle_schema import ENUM_TYPES, RECORD_FIELDS
from european_capital_markets.analytics.bundles import BundleError, _canonical_json

MAX_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 64
MAX_STRING = 262144
MAX_DIGITS = 4096
MAX_INTEGER_DIGITS = 256
MAX_NODES = 200000
MAX_RECORDS = 20000
_RECORDS = {c.__name__: c for c in RECORD_FIELDS}
_ENUMS = {c.__name__: c for c in ENUM_TYPES}
_HINTS = {c: get_type_hints(c) for c in RECORD_FIELDS}


def _matches(value, hint):
    if isinstance(hint, TypeAliasType):
        return _matches(value, hint.__value__)
    origin = get_origin(hint)
    args = get_args(hint)
    if origin in (Union, UnionType):
        return any(_matches(value, h) for h in args)
    if origin is tuple:
        return type(value) is tuple and all(_matches(v, args[0]) for v in value)
    return type(value) is hint


class _Budget:
    def __init__(self):
        self.nodes = 0
        self.records = 0

    def visit(self, depth, *, record=False):
        self.nodes += 1
        self.records += int(record)
        if depth > MAX_DEPTH or self.nodes > MAX_NODES or self.records > MAX_RECORDS:
            raise BundleError("Bundle structural limit exceeded.")


def _text(value):
    if type(value) is not str or len(value) > MAX_STRING:
        raise BundleError("Invalid or oversized string.")
    # UTF-8 has no representation for unpaired surrogate code points.
    value.encode("utf-8", errors="strict")
    return value


def _integer(value):
    if type(value) is not int or value.bit_length() > MAX_INTEGER_DIGITS * 4:
        raise BundleError("Invalid or oversized integer.")
    if len(str(abs(value))) > MAX_INTEGER_DIGITS:
        raise BundleError("Integer digit limit exceeded.")
    return value


def _encode(value, budget, depth=0):
    budget.visit(depth, record=type(value) in RECORD_FIELDS)
    kind = type(value)
    if kind in RECORD_FIELDS:
        names = RECORD_FIELDS[kind]
        if tuple(f.name for f in fields(kind)) != names:
            raise BundleError("Runtime record fields differ from the v1 schema.")
        for name, hint in _HINTS[kind].items():
            if not _matches(getattr(value, name), hint):
                raise BundleError(f"Invalid runtime type: {kind.__name__}.{name}.")
        return {
            "t": kind.__name__,
            "f": {n: _encode(getattr(value, n), budget, depth + 1) for n in names},
        }
    if kind in ENUM_TYPES:
        return {"t": "enum", "e": kind.__name__, "v": value.value}
    if isinstance(value, Enum):
        raise BundleError("Unsupported enum type.")
    if value is None:
        return {"t": "null"}
    if kind in (str, int, bool):
        scalar = (
            _text(value) if kind is str else _integer(value) if kind is int else value
        )
        return {"t": {str: "str", int: "int", bool: "bool"}[kind], "v": scalar}
    if kind is tuple:
        return {"t": "tuple", "v": [_encode(v, budget, depth + 1) for v in value]}
    if kind is Decimal:
        if not value.is_finite():
            raise BundleError("Nonfinite Decimal.")
        sign, digits, exponent = value.as_tuple()
        if len(digits) > MAX_DIGITS:
            raise BundleError("Decimal coefficient limit exceeded.")
        return {
            "t": "decimal",
            "s": sign,
            "d": "".join(map(str, digits)),
            "x": _integer(exponent),
        }
    if kind is datetime:
        if value.tzinfo is not None and type(value.tzinfo) is not timezone:
            raise BundleError("Only fixed-offset timezone values are supported.")
        offset = value.utcoffset()
        micros = (
            None
            if offset is None
            else (
                offset.days * 86400000000
                + offset.seconds * 1000000
                + offset.microseconds
            )
        )
        return {
            "t": "datetime",
            "v": value.replace(tzinfo=None).isoformat(timespec="microseconds"),
            "o": micros,
            "fold": value.fold,
            "z": None if value.tzinfo is None else _text(value.tzname()),
        }
    if kind is date:
        return {"t": "date", "v": value.isoformat()}
    raise BundleError(f"Unsupported runtime type: {kind.__name__}.")


def encode(value):
    try:
        content = _canonical_json(_encode(value, _Budget()))
        if len(content) > MAX_BYTES:
            raise BundleError("Bundle byte limit exceeded.")
        _preflight(content)
        return content
    except (
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        DecimalException,
    ) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError("Cannot encode bundle content.") from exc


def _keys(node, names):
    if set(node) != set(names.split()):
        raise BundleError("Unknown or missing wire fields.")


def _decode(node, budget, depth=0):
    if type(node) is not dict or type(node.get("t")) is not str:
        raise BundleError("Expected a tagged object.")
    tag = node["t"]
    budget.visit(depth, record=tag in _RECORDS)
    if tag in _RECORDS:
        _keys(node, "t f")
        cls = _RECORDS[tag]
        if type(node["f"]) is not dict or set(node["f"]) != set(RECORD_FIELDS[cls]):
            raise BundleError("Unknown or missing record fields.")
        values = {n: _decode(v, budget, depth + 1) for n, v in node["f"].items()}
        if any(not _matches(values[n], h) for n, h in _HINTS[cls].items()):
            raise BundleError(f"Invalid field type for {tag}.")
        return cls(**values)
    if tag == "null":
        _keys(node, "t")
        return None
    if tag == "enum":
        _keys(node, "t e v")
        if type(node["e"]) is not str or type(node["v"]) not in (str, int):
            raise BundleError("Invalid enum encoding.")
        enum = _ENUMS[node["e"]]
        if type(node["v"]) is not type(next(iter(enum)).value):
            raise BundleError("Invalid enum value type.")
        return enum(node["v"])
    if tag == "decimal":
        _keys(node, "t s d x")
        if type(node["s"]) is not int or node["s"] not in (0, 1):
            raise BundleError("Invalid Decimal sign.")
        digits = _text(node["d"])
        if not 1 <= len(digits) <= MAX_DIGITS or re.fullmatch("[0-9]+", digits) is None:
            raise BundleError("Invalid Decimal coefficient.")
        exponent = _integer(node["x"])
        if exponent < MIN_ETINY or exponent + len(digits) - 1 > MAX_EMAX:
            raise BundleError("Decimal exponent outside runtime representation limits.")
        return Decimal((node["s"], tuple(map(int, digits)), exponent))
    if tag == "datetime":
        _keys(node, "t v o fold z")
        if type(node["fold"]) is not int or node["fold"] not in (0, 1):
            raise BundleError("Invalid datetime fold.")
        wall = datetime.fromisoformat(_text(node["v"]))
        if wall.tzinfo is not None:
            raise BundleError("Wall time must not contain an offset.")
        if node["o"] is None:
            if node["z"] is not None:
                raise BundleError("Naive datetime cannot have a timezone name.")
            tz = None
        else:
            tz = timezone(timedelta(microseconds=_integer(node["o"])), _text(node["z"]))
        return wall.replace(tzinfo=tz, fold=node["fold"])
    _keys(node, "t v")
    value = node["v"]
    if tag == "str":
        return _text(value)
    if tag == "int":
        return _integer(value)
    if tag == "bool" and type(value) is bool:
        return value
    if tag == "date":
        return date.fromisoformat(_text(value))
    if tag == "tuple" and type(value) is list:
        return tuple(_decode(v, budget, depth + 1) for v in value)
    raise BundleError("Unknown tag or invalid scalar.")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("Duplicate JSON key.")
        result[key] = value
    return result


def _preflight(content):
    if len(content) > MAX_BYTES:
        raise BundleError("Bundle byte limit exceeded.")
    depth = 0
    quoted = escaped = False
    for byte in content:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                raise BundleError("JSON nesting limit exceeded.")
        elif byte in (93, 125):
            depth -= 1


def _parse_int(text):
    if len(text.lstrip("-")) > MAX_INTEGER_DIGITS:
        raise BundleError("Integer token limit exceeded.")
    return int(text)


def _no_float(_):
    raise BundleError("JSON floats/constants are unsupported.")


def decode(content):
    try:
        _preflight(content)
        node = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_parse_int,
            parse_float=_no_float,
            parse_constant=_no_float,
        )
        value = _decode(node, _Budget())
        if encode(value) != content:
            raise BundleError("Noncanonical bundle bytes.")
        return value
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
        DecimalException,
    ) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError("Malformed bundle content.") from exc
