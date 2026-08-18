"""Flattens gem5's config.json into dot/bracket-path key/value rows.

Nested dicts become dotted paths (system.cpu.numThreads), lists become
bracketed indices (system.mem_ranges[0]), and dicts inside lists compose the
two (system.ruby.network.int_links[0].latency). This makes the full
simulated-system configuration filterable/queryable the same way stats are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ParamRow:
    key: str
    value_text: str | None
    value_num: float | None
    value_type: str  # 'str' | 'int' | 'float' | 'bool' | 'null'


def _classify(value) -> tuple[str | None, float | None, str]:
    if value is None:
        return None, None, "null"
    if isinstance(value, bool):
        # bool must be checked before int - bool is an int subclass in Python.
        return str(value).lower(), (1.0 if value else 0.0), "bool"
    if isinstance(value, int):
        return str(value), float(value), "int"
    if isinstance(value, float):
        return repr(value), (None if math.isnan(value) else value), "float"
    if isinstance(value, str):
        # Deliberately no numeric coercion of strings (e.g. "2147483648:2415919104"
        # looks numeric-ish but isn't a single number) - avoids false positives
        # in numeric --param filters.
        return value, None, "str"
    return str(value), None, "str"


def _walk(obj, path: str, out: list[ParamRow]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else str(k)
            _walk(v, child_path, out)
    elif isinstance(obj, list):
        if not obj:
            out.append(ParamRow(key=path, value_text=None, value_num=None, value_type="null"))
        else:
            for i, v in enumerate(obj):
                _walk(v, f"{path}[{i}]", out)
    else:
        value_text, value_num, value_type = _classify(obj)
        out.append(ParamRow(key=path, value_text=value_text, value_num=value_num, value_type=value_type))


def flatten_config(config: dict) -> list[ParamRow]:
    out: list[ParamRow] = []
    _walk(config, "", out)
    return out
