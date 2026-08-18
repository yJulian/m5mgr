"""Parser for gem5's stats.txt.

A stats.txt file contains one or more "dumps" delimited by:

    ---------- Begin Simulation Statistics ----------
    ...
    ----------   End Simulation Statistics   ----------

Within a dump, most lines look like:

    <key>   <value> [<pct>% <cum_pct>%]   [# <description>] (<Unit>)

Distribution-style stats (e.g. gem5's Histogram/VectorDistribution) print a
sequence of pipe-separated groups instead of a single value:

    <key>   | <v0> <p0>% <cp0>% | <v1> <p1>% <cp1>% | ...   (<Unit>)

which we expand into one StatRow per group, keyed as "<key>::<i>".

Values that don't parse as a float (notably the literal "nan") are kept as
NULL numeric value while the raw token is preserved in value_text - this
must never raise.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_BEGIN_RE = re.compile(r"^-+\s*Begin Simulation Statistics\s*-+\s*$")
_END_RE = re.compile(r"^-+\s*End Simulation Statistics\s*-+\s*$")
# The unit is always the last parenthesized group on the line, even when the
# description text itself contains parens (e.g. "(inst/s) ((Count/Second))").
_TRAILING_UNIT_RE = re.compile(r"\(([^()]*)\)\s*$")


@dataclass
class StatRow:
    key: str
    value: float | None
    value_text: str
    percent: float | None = None
    cum_percent: float | None = None
    unit: str | None = None
    description: str | None = None


@dataclass
class Dump:
    index: int
    line_start: int
    line_end: int | None = None
    complete: bool = False
    rows: list[StatRow] = field(default_factory=list)


def _parse_num(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    # float("nan") parses successfully in Python but isn't a usable numeric
    # value for storage/comparison - keep it NULL, the raw text is preserved
    # separately in value_text.
    return None if math.isnan(value) else value


def _parse_pct(text: str) -> float | None:
    return _parse_num(text.rstrip("%"))


def parse_stat_line(line: str) -> list[StatRow]:
    """Parse one non-empty stat line into one or more StatRows."""
    unit_match = _TRAILING_UNIT_RE.search(line)
    if unit_match:
        unit = unit_match.group(1).strip() or None
        remainder = line[: unit_match.start()]
    else:
        unit = None
        remainder = line

    if "#" in remainder:
        left, _, description = remainder.partition("#")
        description = description.strip() or None
    else:
        left, description = remainder, None

    tokens = left.split()
    if not tokens:
        return []
    key = tokens[0]
    rest = tokens[1:]

    if "|" in rest:
        groups: list[list[str]] = []
        current: list[str] = []
        for tok in rest:
            if tok == "|":
                if current:
                    groups.append(current)
                    current = []
            else:
                current.append(tok)
        if current:
            groups.append(current)

        rows = []
        for i, group in enumerate(groups):
            value_text = group[0] if group else ""
            percent = _parse_pct(group[1]) if len(group) >= 2 else None
            cum_percent = _parse_pct(group[2]) if len(group) >= 3 else None
            rows.append(
                StatRow(
                    key=f"{key}::{i}",
                    value=_parse_num(value_text),
                    value_text=value_text,
                    percent=percent,
                    cum_percent=cum_percent,
                    unit=unit,
                    description=description,
                )
            )
        return rows

    if len(rest) >= 3:
        value_text = rest[0]
        percent = _parse_pct(rest[1])
        cum_percent = _parse_pct(rest[2])
    elif len(rest) >= 1:
        value_text = rest[0]
        percent = None
        cum_percent = None
    else:
        value_text = ""
        percent = None
        cum_percent = None

    return [
        StatRow(
            key=key,
            value=_parse_num(value_text),
            value_text=value_text,
            percent=percent,
            cum_percent=cum_percent,
            unit=unit,
            description=description,
        )
    ]


def parse_stats_text(text: str) -> list[Dump]:
    dumps: list[Dump] = []
    current: Dump | None = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip("\n")
        if _BEGIN_RE.match(line.strip()):
            current = Dump(index=len(dumps), line_start=lineno)
            continue
        if _END_RE.match(line.strip()):
            if current is not None:
                current.line_end = lineno
                current.complete = True
                dumps.append(current)
                current = None
            continue
        if current is None:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        current.rows.extend(parse_stat_line(stripped))

    if current is not None:
        # EOF while still inside a block (crashed/truncated run) - keep the
        # partial data rather than discarding it.
        current.complete = False
        dumps.append(current)

    return dumps


def parse_stats_file(path) -> list[Dump]:
    with open(path, "r", errors="replace") as f:
        return parse_stats_text(f.read())
