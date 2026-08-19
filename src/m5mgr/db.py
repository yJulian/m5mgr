"""SQLite schema and query layer shared by the CLI and the web app.

This module is the single source of truth for reading/writing run data -
cli.py and web/app.py both call into it rather than issuing their own SQL,
so both surfaces stay consistent with each other by construction.
"""

from __future__ import annotations

import fnmatch
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config_flattener import ParamRow
from .stats_parser import Dump

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    source            TEXT NOT NULL CHECK (source IN ('run','import')),
    status            TEXT NOT NULL CHECK (status IN ('completed','failed')),
    gem5_bin          TEXT,
    gem5_args         TEXT,
    exit_code         INTEGER,
    duration_seconds  REAL,
    m5out_dir         TEXT NOT NULL,
    source_path       TEXT,
    host              TEXT,
    n_dumps           INTEGER NOT NULL DEFAULT 0,
    tags              TEXT,
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_name ON runs(name);

CREATE TABLE IF NOT EXISTS dumps (
    run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    dump_index  INTEGER NOT NULL,
    line_start  INTEGER NOT NULL,
    line_end    INTEGER,
    complete    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (run_id, dump_index)
);

CREATE TABLE IF NOT EXISTS stats (
    run_id       TEXT NOT NULL,
    dump_index   INTEGER NOT NULL,
    key          TEXT NOT NULL,
    value        REAL,
    value_text   TEXT NOT NULL,
    percent      REAL,
    cum_percent  REAL,
    unit         TEXT,
    description  TEXT,
    PRIMARY KEY (run_id, dump_index, key),
    FOREIGN KEY (run_id, dump_index) REFERENCES dumps(run_id, dump_index) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_stats_key ON stats(key);
CREATE INDEX IF NOT EXISTS idx_stats_run ON stats(run_id, dump_index);

CREATE TABLE IF NOT EXISTS params (
    run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value_text  TEXT,
    value_num   REAL,
    value_type  TEXT NOT NULL CHECK (value_type IN ('str','int','float','bool','null')),
    PRIMARY KEY (run_id, key)
);
CREATE INDEX IF NOT EXISTS idx_params_key ON params(key);
"""


class RunNotFoundError(LookupError):
    pass


class AmbiguousRefError(LookupError):
    def __init__(self, ref: str, matches: list[sqlite3.Row]):
        self.ref = ref
        self.matches = matches
        described = ", ".join(f"{m['id']} ({m['name']}, {m['created_at']})" for m in matches)
        super().__init__(f"Reference {ref!r} is ambiguous, matches: {described}")


@dataclass
class RunRecord:
    id: str
    name: str
    created_at: str
    source: str
    status: str
    m5out_dir: str
    gem5_bin: str | None = None
    gem5_args: str | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    source_path: str | None = None
    host: str | None = None
    n_dumps: int = 0
    tags: str | None = None
    notes: str | None = None


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_run(conn: sqlite3.Connection, run: RunRecord) -> None:
    conn.execute(
        """
        INSERT INTO runs (
            id, name, created_at, source, status, gem5_bin, gem5_args,
            exit_code, duration_seconds, m5out_dir, source_path, host,
            n_dumps, tags, notes
        ) VALUES (
            :id, :name, :created_at, :source, :status, :gem5_bin, :gem5_args,
            :exit_code, :duration_seconds, :m5out_dir, :source_path, :host,
            :n_dumps, :tags, :notes
        )
        """,
        vars(run),
    )
    conn.commit()


def insert_dumps(conn: sqlite3.Connection, run_id: str, dumps: list[Dump]) -> None:
    conn.executemany(
        "INSERT INTO dumps (run_id, dump_index, line_start, line_end, complete) "
        "VALUES (?, ?, ?, ?, ?)",
        [(run_id, d.index, d.line_start, d.line_end, int(d.complete)) for d in dumps],
    )
    conn.commit()


def insert_stats(conn: sqlite3.Connection, run_id: str, dumps: list[Dump]) -> None:
    rows = [
        (
            run_id,
            d.index,
            r.key,
            r.value,
            r.value_text,
            r.percent,
            r.cum_percent,
            r.unit,
            r.description,
        )
        for d in dumps
        for r in d.rows
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO stats "
        "(run_id, dump_index, key, value, value_text, percent, cum_percent, unit, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def insert_params(conn: sqlite3.Connection, run_id: str, params: list[ParamRow]) -> None:
    rows = [(run_id, p.key, p.value_text, p.value_num, p.value_type) for p in params]
    conn.executemany(
        "INSERT OR REPLACE INTO params (run_id, key, value_text, value_num, value_type) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def get_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


def resolve_ref(conn: sqlite3.Connection, ref: str) -> sqlite3.Row:
    """Resolve a run id, id-prefix, or run name to a single run row.

    Lookup order: exact id, then unique id-prefix, then exact name (which
    raises AmbiguousRefError if more than one run shares that name - names
    are not required to be unique).
    """
    row = get_run(conn, ref)
    if row is not None:
        return row

    prefix_matches = conn.execute(
        "SELECT * FROM runs WHERE id LIKE ? ORDER BY created_at DESC", (ref + "%",)
    ).fetchall()
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise AmbiguousRefError(ref, prefix_matches)

    name_matches = conn.execute(
        "SELECT * FROM runs WHERE name = ? ORDER BY created_at DESC", (ref,)
    ).fetchall()
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        raise AmbiguousRefError(ref, name_matches)

    raise RunNotFoundError(f"No run found matching id/name {ref!r}")


def last_dump_index(conn: sqlite3.Connection, run_id: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(dump_index) AS m FROM dumps WHERE run_id = ?", (run_id,)
    ).fetchone()
    return row["m"] if row and row["m"] is not None else None


_NUMERIC_OPS = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _run_matches_stat_filter(conn: sqlite3.Connection, run_id: str, key_glob: str, op: str, value: float) -> bool:
    dump_index = last_dump_index(conn, run_id)
    if dump_index is None:
        return False
    all_keys = conn.execute(
        "SELECT key, value FROM stats WHERE run_id = ? AND dump_index = ?", (run_id, dump_index)
    ).fetchall()
    cmp_fn = _NUMERIC_OPS[op]
    for r in all_keys:
        if fnmatch.fnmatch(r["key"], key_glob) and r["value"] is not None and cmp_fn(r["value"], value):
            return True
    return False


def _run_matches_param_filter(conn: sqlite3.Connection, run_id: str, key_glob: str, op: str, value: str) -> bool:
    rows = conn.execute("SELECT key, value_text FROM params WHERE run_id = ?", (run_id,)).fetchall()
    for r in rows:
        if not fnmatch.fnmatch(r["key"], key_glob):
            continue
        text = r["value_text"]
        if text is None:
            continue
        if op == "=" and text == value:
            return True
        if op == "!=" and text != value:
            return True
        if op == "~" and value in text:
            return True
    return False


def list_runs(
    conn: sqlite3.Connection,
    *,
    name_glob: str | None = None,
    tag: str | None = None,
    stat_filters: tuple[tuple[str, str, float], ...] = (),
    param_filters: tuple[tuple[str, str, str], ...] = (),
    match: str = "all",
    sort: str = "created_at",
) -> list[sqlite3.Row]:
    """List runs, narrowed by name/tag (always required if given) and by
    stat/param filters, which are combined with each other according to
    `match`: "all" (AND - a run must satisfy every filter, the default) or
    "any" (OR - a run must satisfy at least one filter).
    """
    if match not in ("all", "any"):
        raise ValueError(f"match must be 'all' or 'any', got {match!r}")

    sort_column = sort if sort in ("created_at", "name") else "created_at"
    rows = conn.execute(f"SELECT * FROM runs ORDER BY {sort_column} DESC").fetchall()

    if name_glob:
        rows = [r for r in rows if fnmatch.fnmatch(r["name"], name_glob)]
    if tag:
        rows = [r for r in rows if tag in [t.strip() for t in (r["tags"] or "").split(",") if t.strip()]]

    predicates = [
        (lambda r, kg=kg, op=op, v=v: _run_matches_stat_filter(conn, r["id"], kg, op, v))
        for kg, op, v in stat_filters
    ] + [
        (lambda r, kg=kg, op=op, v=v: _run_matches_param_filter(conn, r["id"], kg, op, v))
        for kg, op, v in param_filters
    ]
    if predicates:
        combine = all if match == "all" else any
        rows = [r for r in rows if combine(p(r) for p in predicates)]

    return rows


def get_stats(
    conn: sqlite3.Connection, run_id: str, dump_index: int, key_globs: tuple[str, ...] = ()
) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM stats WHERE run_id = ? AND dump_index = ? ORDER BY key", (run_id, dump_index)
    ).fetchall()
    if key_globs:
        rows = [r for r in rows if any(fnmatch.fnmatch(r["key"], g) for g in key_globs)]
    return rows


def get_params(
    conn: sqlite3.Connection, run_id: str, key_globs: tuple[str, ...] = ()
) -> list[sqlite3.Row]:
    rows = conn.execute("SELECT * FROM params WHERE run_id = ? ORDER BY key", (run_id,)).fetchall()
    if key_globs:
        rows = [r for r in rows if any(fnmatch.fnmatch(r["key"], g) for g in key_globs)]
    return rows


def compare_stats(
    conn: sqlite3.Connection,
    run_ids: list[str],
    dump_by_run: dict[str, int] | None = None,
    key_globs: tuple[str, ...] = (),
    baseline_index: int | None = 0,
) -> dict:
    """Compare stats across runs. `run_ids[baseline_index]` is the baseline
    deltas/pct_changes are computed against (default: the first run); pass
    `baseline_index=None` to skip computing deltas/pct_changes entirely."""
    dump_by_run = dump_by_run or {}
    runs_meta = []
    per_run_stats: dict[str, dict[str, sqlite3.Row]] = {}

    for run_id in run_ids:
        run = get_run(conn, run_id)
        dump_index = dump_by_run.get(run_id, last_dump_index(conn, run_id))
        runs_meta.append({"id": run_id, "name": run["name"] if run else run_id, "dump_index": dump_index})
        if dump_index is None:
            per_run_stats[run_id] = {}
        else:
            rows = get_stats(conn, run_id, dump_index, key_globs)
            per_run_stats[run_id] = {r["key"]: r for r in rows}

    all_keys = sorted({k for stats in per_run_stats.values() for k in stats})

    result_rows = []
    for key in all_keys:
        values = []
        unit = None
        for run_id in run_ids:
            row = per_run_stats[run_id].get(key)
            values.append(row["value"] if row else None)
            if row and row["unit"] and unit is None:
                unit = row["unit"]
        baseline = (
            values[baseline_index]
            if baseline_index is not None and 0 <= baseline_index < len(values)
            else None
        )
        deltas = []
        pct_changes = []
        for v in values:
            if v is None or baseline is None:
                deltas.append(None)
                pct_changes.append(None)
            else:
                delta = v - baseline
                deltas.append(delta)
                pct_changes.append((delta / baseline * 100) if baseline != 0 else None)
        result_rows.append(
            {"key": key, "unit": unit, "values": values, "deltas": deltas, "pct_changes": pct_changes}
        )

    return {"runs": runs_meta, "rows": result_rows, "baseline_index": baseline_index}


def compare_params(
    conn: sqlite3.Connection,
    run_ids: list[str],
    key_globs: tuple[str, ...] = (),
) -> dict:
    runs_meta = []
    per_run_params: dict[str, dict[str, sqlite3.Row]] = {}

    for run_id in run_ids:
        run = get_run(conn, run_id)
        runs_meta.append({"id": run_id, "name": run["name"] if run else run_id})
        rows = get_params(conn, run_id, key_globs)
        per_run_params[run_id] = {r["key"]: r for r in rows}

    all_keys = sorted({k for params in per_run_params.values() for k in params})

    result_rows = []
    for key in all_keys:
        values = []
        for run_id in run_ids:
            row = per_run_params[run_id].get(key)
            values.append(row["value_text"] if row else None)
        result_rows.append({"key": key, "values": values})

    return {"runs": runs_meta, "rows": result_rows}


def delete_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    conn.commit()
