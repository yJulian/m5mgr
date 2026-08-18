"""m5mgr command-line interface."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from . import config, db, formatting, ingest, runner
from .ids import generate_run_id

USAGE = """\
usage: m5mgr <command> [args]

commands:
  run      --name NAME [--outdir DIR] [--tag TAG]... [--notes TEXT] -- <gem5 args...>
  import   PATH --name NAME [--tag TAG]... [--notes TEXT] [--move]
  list     [--name PATTERN] [--tag TAG] [--stat EXPR]... [--param EXPR]... [--sort created_at|name] [--format table|csv]
  show     REF [--dump N | --all-dumps] [--stat GLOB]... [--param GLOB]... [--format table|csv]
  compare  REF REF... [--dump N] [--stat GLOB]... [--param GLOB]... [--format table|csv] [--output FILE]
  rm       REF [--keep-files] [--yes]
  web      [--host HOST] [--port PORT] [--debug]

env vars:
  GEM5_BIN     path to the gem5 executable (required for `run`)
  M5MGR_HOME   where the db and managed run store live (default ~/.local/share/m5mgr)
  M5MGR_SCOPE  isolates runs per project/workspace within M5MGR_HOME (default 'default')
"""


def _run_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="m5mgr run")
    p.add_argument("--name", required=True)
    p.add_argument("--outdir", default=None, help="m5out directory; default: new temp dir under /tmp")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--notes", default=None)
    p.add_argument("--id-only", action="store_true")
    return p


def cmd_run(args_before: list[str], passthrough: list[str]) -> int:
    ns = _run_arg_parser().parse_args(args_before)

    if not passthrough:
        print("error: no gem5 arguments given after `--`", file=sys.stderr)
        return 2

    try:
        gem5_bin = config.gem5_bin()
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        runner.check_passthrough_args(passthrough)
    except runner.PassthroughArgError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    run_id = generate_run_id()
    user_outdir = ns.outdir is not None
    staging_dir = Path(ns.outdir) if user_outdir else Path(tempfile.mkdtemp(prefix="m5mgr-"))
    staging_dir.mkdir(parents=True, exist_ok=True)

    exit_code, duration = runner.run_gem5(
        gem5_bin,
        str(staging_dir),
        passthrough,
        stdout_path=staging_dir / "m5mgr.stdout.log",
        stderr_path=staging_dir / "m5mgr.stderr.log",
    )

    conn = db.connect(config.db_path())
    record = ingest.ingest(
        conn,
        source_dir=staging_dir,
        name=ns.name,
        source="run",
        move=not user_outdir,
        gem5_bin=gem5_bin,
        gem5_args=passthrough,
        exit_code=exit_code,
        duration_seconds=duration,
        tags=ns.tag,
        notes=ns.notes,
        run_id=run_id,
    )
    conn.close()

    if ns.id_only:
        print(record.id)
    else:
        print(
            f"Run completed: id={record.id} name={record.name} status={record.status} "
            f"dumps={record.n_dumps} scope={config.scope()}"
        )
    return 0 if record.status == "completed" else 1


def cmd_import(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="m5mgr import")
    p.add_argument("path")
    p.add_argument("--name", required=True)
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--notes", default=None)
    p.add_argument("--move", action="store_true")
    p.add_argument("--id-only", action="store_true")
    ns = p.parse_args(argv)

    conn = db.connect(config.db_path())
    try:
        record = ingest.ingest_existing_dir(
            conn, Path(ns.path), name=ns.name, move=ns.move, tags=ns.tag, notes=ns.notes
        )
    except NotADirectoryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    if ns.id_only:
        print(record.id)
    else:
        print(
            f"Imported: id={record.id} name={record.name} status={record.status} "
            f"dumps={record.n_dumps} scope={config.scope()}"
        )
    return 0


def cmd_list(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="m5mgr list")
    p.add_argument("--name")
    p.add_argument("--tag")
    p.add_argument("--stat", action="append", default=[], help="KEY<op>VALUE, e.g. 'system.cpu.ipc>1.0'")
    p.add_argument("--param", action="append", default=[], help="KEY<op>VALUE, e.g. 'system.cpu.numThreads=4'")
    p.add_argument("--sort", choices=["created_at", "name"], default="created_at")
    p.add_argument("--format", choices=["table", "csv"], default="table")
    ns = p.parse_args(argv)

    try:
        stat_filters = tuple(formatting.parse_stat_filter(e) for e in ns.stat)
        param_filters = tuple(formatting.parse_param_filter(e) for e in ns.param)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    conn = db.connect(config.db_path())
    rows = db.list_runs(
        conn, name_glob=ns.name, tag=ns.tag, stat_filters=stat_filters, param_filters=param_filters, sort=ns.sort
    )
    conn.close()

    headers = ["id", "name", "created_at", "status", "source", "n_dumps", "tags"]
    table_rows = [
        [r["id"], r["name"], r["created_at"], r["status"], r["source"], r["n_dumps"], r["tags"] or ""]
        for r in rows
    ]
    if ns.format == "csv":
        print(formatting.render_csv(headers, table_rows))
    else:
        print(f"Scope: {config.scope()}")
        if table_rows:
            print(formatting.render_table(headers, table_rows))
        else:
            print("No runs found.")
    return 0


def _resolve_or_print_error(conn, ref: str):
    try:
        return db.resolve_ref(conn, ref)
    except (db.AmbiguousRefError, db.RunNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return None


def cmd_show(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="m5mgr show")
    p.add_argument("ref")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--dump", type=int, default=None)
    group.add_argument("--all-dumps", action="store_true")
    p.add_argument("--stat", action="append", default=[], help="glob pattern, repeatable")
    p.add_argument("--param", action="append", default=[], help="glob pattern, repeatable")
    p.add_argument("--format", choices=["table", "csv"], default="table")
    ns = p.parse_args(argv)

    conn = db.connect(config.db_path())
    run = _resolve_or_print_error(conn, ns.ref)
    if run is None:
        conn.close()
        return 2

    print(
        f"id={run['id']} name={run['name']} status={run['status']} "
        f"created_at={run['created_at']} source={run['source']} dumps={run['n_dumps']}"
    )

    if ns.param:
        prows = db.get_params(conn, run["id"], tuple(ns.param))
        headers = ["key", "value", "type"]
        table_rows = [[r["key"], r["value_text"] or "", r["value_type"]] for r in prows]
        print("\nParams:")
        if ns.format == "csv":
            print(formatting.render_csv(headers, table_rows))
        elif table_rows:
            print(formatting.render_table(headers, table_rows))
        else:
            print("  (no matching params)")

    if ns.all_dumps:
        dump_indices = [
            row["dump_index"]
            for row in conn.execute(
                "SELECT dump_index FROM dumps WHERE run_id = ? ORDER BY dump_index", (run["id"],)
            ).fetchall()
        ]
    elif ns.dump is not None:
        dump_indices = [ns.dump]
    else:
        last = db.last_dump_index(conn, run["id"])
        dump_indices = [last] if last is not None else []

    for di in dump_indices:
        srows = db.get_stats(conn, run["id"], di, tuple(ns.stat))
        headers = ["key", "value", "unit", "description"]
        table_rows = [
            [r["key"], formatting.format_number(r["value"]) if r["value"] is not None else r["value_text"],
             r["unit"] or "", r["description"] or ""]
            for r in srows
        ]
        print(f"\nDump {di}:")
        if ns.format == "csv":
            print(formatting.render_csv(headers, table_rows))
        elif table_rows:
            print(formatting.render_table(headers, table_rows))
        else:
            print("  (no matching stats)")

    conn.close()
    return 0


def cmd_compare(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="m5mgr compare")
    p.add_argument("refs", nargs="+")
    p.add_argument("--dump", type=int, default=None, help="dump index for all runs; default: each run's last dump")
    p.add_argument("--stat", action="append", default=[])
    p.add_argument("--param", action="append", default=[])
    p.add_argument("--format", choices=["table", "csv"], default="table")
    p.add_argument("--output")
    ns = p.parse_args(argv)

    if len(ns.refs) < 2:
        print("error: compare requires at least 2 run references", file=sys.stderr)
        return 2

    conn = db.connect(config.db_path())
    runs = []
    for ref in ns.refs:
        run = _resolve_or_print_error(conn, ref)
        if run is None:
            conn.close()
            return 2
        runs.append(run)

    run_ids = [r["id"] for r in runs]
    dump_by_run = {rid: ns.dump for rid in run_ids} if ns.dump is not None else None

    outputs = []

    if not ns.param or ns.stat:
        result = db.compare_stats(conn, run_ids, dump_by_run=dump_by_run, key_globs=tuple(ns.stat))
        headers = ["key", "unit"] + [f"{rm['name']} ({rm['id']})" for rm in result["runs"]]
        two_run = len(run_ids) == 2
        if two_run:
            headers += ["delta", "pct_change"]
        table_rows = []
        for row in result["rows"]:
            cells = [row["key"], row["unit"] or ""]
            cells += [formatting.format_number(v) for v in row["values"]]
            if two_run:
                cells.append(formatting.format_number(row["deltas"][1]))
                pct = row["pct_changes"][1]
                cells.append(f"{pct:.2f}%" if pct is not None else formatting.MISSING)
            table_rows.append(cells)
        outputs.append(("Stats", headers, table_rows))

    if ns.param:
        result = db.compare_params(conn, run_ids, key_globs=tuple(ns.param))
        headers = ["key"] + [f"{rm['name']} ({rm['id']})" for rm in result["runs"]]
        table_rows = [[row["key"]] + [v if v is not None else formatting.MISSING for v in row["values"]]
                      for row in result["rows"]]
        outputs.append(("Params", headers, table_rows))

    conn.close()

    rendered_parts = []
    for title, headers, table_rows in outputs:
        body = formatting.render_csv(headers, table_rows) if ns.format == "csv" else formatting.render_table(headers, table_rows)
        rendered_parts.append(body if ns.format == "csv" or len(outputs) == 1 else f"{title}:\n{body}")
    output_text = "\n\n".join(rendered_parts)

    if ns.output:
        Path(ns.output).write_text(output_text + ("\n" if not output_text.endswith("\n") else ""))
        print(f"Wrote comparison to {ns.output}")
    else:
        print(output_text)
    return 0


def cmd_rm(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="m5mgr rm")
    p.add_argument("ref")
    p.add_argument("--keep-files", action="store_true")
    p.add_argument("--yes", action="store_true")
    ns = p.parse_args(argv)

    conn = db.connect(config.db_path())
    run = _resolve_or_print_error(conn, ns.ref)
    if run is None:
        conn.close()
        return 2

    if not ns.yes:
        answer = input(f"Delete run {run['id']} ({run['name']})? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            conn.close()
            return 1

    run_id = run["id"]
    db.delete_run(conn, run_id)
    conn.close()

    if not ns.keep_files:
        run_dir = config.run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)

    print(f"Deleted run {run_id}")
    return 0


def cmd_web(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="m5mgr web")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--debug", action="store_true")
    ns = p.parse_args(argv)

    from .web.app import create_app

    app = create_app()
    app.run(host=ns.host, port=ns.port, debug=ns.debug)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd == "run":
        if "--" not in rest:
            print(
                "error: `m5mgr run` requires a `--` separator before gem5 arguments, e.g.\n"
                "  m5mgr run --name my-run -- -re myconfig.py --opt=1",
                file=sys.stderr,
            )
            return 2
        idx = rest.index("--")
        return cmd_run(rest[:idx], rest[idx + 1:])
    if cmd == "import":
        return cmd_import(rest)
    if cmd == "list":
        return cmd_list(rest)
    if cmd == "show":
        return cmd_show(rest)
    if cmd == "compare":
        return cmd_compare(rest)
    if cmd == "rm":
        return cmd_rm(rest)
    if cmd == "web":
        return cmd_web(rest)

    print(f"error: unknown command {cmd!r}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
