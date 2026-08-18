"""Ingestion pipeline shared by `m5mgr run` and `m5mgr import`.

Copies (or moves) an m5out directory into the managed store, parses
stats.txt and config.json, and writes everything into the SQLite DB as one
run record plus its flattened stats/params rows.
"""

from __future__ import annotations

import json
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path

from . import config, db
from .config_flattener import flatten_config
from .ids import generate_run_id
from .stats_parser import parse_stats_file


def ingest(
    conn,
    *,
    source_dir: Path,
    name: str,
    source: str,
    move: bool = False,
    gem5_bin: str | None = None,
    gem5_args: list[str] | None = None,
    exit_code: int | None = None,
    duration_seconds: float | None = None,
    source_path: str | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
    run_id: str | None = None,
) -> db.RunRecord:
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise NotADirectoryError(f"m5out source directory does not exist: {source_dir}")

    run_id = run_id or generate_run_id()
    dest_m5out = config.run_dir(run_id) / "m5out"
    dest_m5out.parent.mkdir(parents=True, exist_ok=True)

    if move:
        shutil.move(str(source_dir), str(dest_m5out))
    else:
        shutil.copytree(source_dir, dest_m5out)

    stats_path = dest_m5out / "stats.txt"
    dumps = parse_stats_file(stats_path) if stats_path.exists() else []

    config_json_path = dest_m5out / "config.json"
    params = []
    if config_json_path.exists():
        with open(config_json_path) as f:
            params = flatten_config(json.load(f))

    n_dumps = len(dumps)
    status = "completed" if n_dumps >= 1 else "failed"
    if exit_code not in (None, 0):
        status = "failed"

    record = db.RunRecord(
        id=run_id,
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        status=status,
        m5out_dir=str(dest_m5out),
        gem5_bin=gem5_bin,
        gem5_args=json.dumps(gem5_args) if gem5_args is not None else None,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        source_path=source_path,
        host=socket.gethostname(),
        n_dumps=n_dumps,
        tags=",".join(tags) if tags else None,
        notes=notes,
    )

    db.insert_run(conn, record)
    if dumps:
        db.insert_dumps(conn, run_id, dumps)
        db.insert_stats(conn, run_id, dumps)
    if params:
        db.insert_params(conn, run_id, params)

    return record


def ingest_existing_dir(
    conn,
    path: Path,
    *,
    name: str,
    move: bool = False,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> db.RunRecord:
    """Backs `m5mgr import`: ingest a pre-existing m5out dir, no gem5 invocation."""
    path = Path(path)
    return ingest(
        conn,
        source_dir=path,
        name=name,
        source="import",
        move=move,
        source_path=str(path.resolve()),
        tags=tags,
        notes=notes,
    )
