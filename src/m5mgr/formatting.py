"""Table/CSV rendering and filter-expression parsing shared by the CLI and web app."""

from __future__ import annotations

import csv
import io

MISSING = "—"  # em dash

_STAT_OPS = ("!=", ">=", "<=", "=", ">", "<")
_PARAM_OPS = ("!=", "~", "=")


def _split_on_op(expr: str, ops: tuple[str, ...]) -> tuple[str, str, str]:
    best: tuple[int, str] | None = None
    for op in ops:
        idx = expr.find(op)
        if idx == -1:
            continue
        if best is None or idx < best[0] or (idx == best[0] and len(op) > len(best[1])):
            best = (idx, op)
    if best is None:
        raise ValueError(f"No operator ({', '.join(ops)}) found in filter expression {expr!r}")
    idx, op = best
    key = expr[:idx].strip()
    value = expr[idx + len(op):].strip()
    if not key:
        raise ValueError(f"Filter expression {expr!r} is missing a key before the operator")
    return key, op, value


def parse_stat_filter(expr: str) -> tuple[str, str, float]:
    """Parse 'KEY<op>VALUE' (op: =,!=,<,<=,>,>=) into (key_glob, op, numeric value)."""
    key, op, value = _split_on_op(expr, _STAT_OPS)
    try:
        num = float(value)
    except ValueError as e:
        raise ValueError(f"Stat filter {expr!r} has a non-numeric value {value!r}") from e
    return key, op, num


def parse_param_filter(expr: str) -> tuple[str, str, str]:
    """Parse 'KEY<op>VALUE' (op: =,!=,~) into (key_glob, op, text value). ~ means substring."""
    return _split_on_op(expr, _PARAM_OPS)


def format_number(value) -> str:
    if value is None:
        return MISSING
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    str_rows = [[str(c) for c in row] for row in rows]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(row) for row in str_rows)
    return "\n".join(lines)


def render_csv(headers: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()
