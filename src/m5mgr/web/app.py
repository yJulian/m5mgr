"""Read-only Flask dashboard for browsing/comparing runs.

Reads from the exact same SQLite DB the CLI writes to via db.py/formatting.py
- no separate query layer, so the CLI and the web app never disagree.
"""

from __future__ import annotations

from urllib.parse import urlencode

from flask import Flask, Response, abort, g, redirect, render_template, request, send_from_directory, url_for

from .. import config, db, formatting


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["M5MGR_DB_PATH"] = str(db_path) if db_path else str(config.db_path())
    app.jinja_env.globals["m5mgr_scope"] = config.scope()
    app.jinja_env.globals["format_number"] = formatting.format_number

    def _multi_arg(name: str) -> tuple[str, ...]:
        """Query args for `name`, splitting each on commas so one text box can
        hold several filter/glob expressions at once (OR'd together by
        get_stats/get_params/list_runs's default "any" glob matching)."""
        return tuple(s.strip() for e in request.args.getlist(name) for s in e.split(",") if s.strip())

    def get_conn():
        if "conn" not in g:
            g.conn = db.connect(app.config["M5MGR_DB_PATH"])
            g.conn.execute("PRAGMA query_only = ON")
        return g.conn

    @app.teardown_appcontext
    def close_conn(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.route("/")
    def index():
        return redirect(url_for("runs_list"))

    @app.route("/runs")
    def runs_list():
        conn = get_conn()
        name = request.args.get("name") or None
        tag = request.args.get("tag") or None
        stat_exprs = _multi_arg("stat")
        param_exprs = _multi_arg("param")
        match = request.args.get("match") or "all"
        try:
            stat_filters = tuple(formatting.parse_stat_filter(e) for e in stat_exprs)
            param_filters = tuple(formatting.parse_param_filter(e) for e in param_exprs)
            rows = db.list_runs(
                conn, name_glob=name, tag=tag, stat_filters=stat_filters, param_filters=param_filters, match=match,
            )
        except ValueError as e:
            return render_template("runs_list.html", runs=[], error=str(e), filters=request.args)
        return render_template("runs_list.html", runs=rows, error=None, filters=request.args)

    @app.route("/runs/<ref>")
    def run_detail(ref):
        conn = get_conn()
        try:
            run = db.resolve_ref(conn, ref)
        except db.AmbiguousRefError as e:
            return render_template("run_detail.html", ambiguous=e.matches, ref=ref, run=None)
        except db.RunNotFoundError:
            abort(404)

        stat_globs = _multi_arg("stat")
        param_globs = _multi_arg("param")
        dump_param = request.args.get("dump")
        all_dumps_flag = request.args.get("all_dumps") == "1"

        dumps = conn.execute(
            "SELECT dump_index, complete FROM dumps WHERE run_id = ? ORDER BY dump_index", (run["id"],)
        ).fetchall()
        last = db.last_dump_index(conn, run["id"])

        if all_dumps_flag:
            selected_dumps = [d["dump_index"] for d in dumps]
        elif dump_param is not None:
            selected_dumps = [int(dump_param)]
        else:
            selected_dumps = [last] if last is not None else []

        dump_stats = {di: db.get_stats(conn, run["id"], di, stat_globs) for di in selected_dumps}
        params = db.get_params(conn, run["id"], param_globs) if param_globs else []

        return render_template(
            "run_detail.html",
            ambiguous=None,
            run=run,
            dumps=dumps,
            selected_dumps=selected_dumps,
            dump_stats=dump_stats,
            params=params,
            stat_globs=", ".join(stat_globs),
            param_globs=", ".join(param_globs),
            all_dumps_flag=all_dumps_flag,
        )

    @app.route("/runs/<ref>/files/<path:name>")
    def run_file(ref, name):
        conn = get_conn()
        try:
            run = db.resolve_ref(conn, ref)
        except (db.AmbiguousRefError, db.RunNotFoundError):
            abort(404)
        return send_from_directory(run["m5out_dir"], name)

    @app.route("/compare")
    def compare():
        conn = get_conn()
        run_refs = [r for r in request.args.getlist("run") if r]
        if len(run_refs) < 2:
            return render_template("compare.html", error="Select at least 2 runs to compare.", result=None, param_result=None)

        runs = []
        for ref in run_refs:
            try:
                runs.append(db.resolve_ref(conn, ref))
            except (db.AmbiguousRefError, db.RunNotFoundError) as e:
                return render_template("compare.html", error=str(e), result=None, param_result=None)

        run_ids = [r["id"] for r in runs]
        stat_globs = _multi_arg("stat")
        param_globs = _multi_arg("param")
        dump_param = request.args.get("dump")
        dump_by_run = {rid: int(dump_param) for rid in run_ids} if dump_param else None

        # No baseline column is selected until the user clicks one - only
        # then do stat cells grow a "(+pct%)" relative to it.
        baseline_ref = request.args.get("baseline")
        baseline_index = run_ids.index(baseline_ref) if baseline_ref in run_ids else None

        # Mirrors `m5mgr compare`'s CLI behavior: stats show unless --param is
        # given without --stat, in which case only params are compared.
        show_stats = not param_globs or stat_globs
        result = (
            db.compare_stats(conn, run_ids, dump_by_run=dump_by_run, key_globs=stat_globs, baseline_index=baseline_index)
            if show_stats else None
        )
        param_result = db.compare_params(conn, run_ids, key_globs=param_globs) if param_globs else None

        # Column-header "set as baseline" links reuse every current query
        # param except `baseline`/`format` itself.
        base_qs = urlencode([(k, v) for k, v in request.args.items(multi=True) if k not in ("baseline", "format")])

        fmt = request.args.get("format")
        if fmt == "csv" and result is not None:
            headers = ["key", "unit"] + [rm["name"] or rm["id"] for rm in result["runs"]]
            rows = [
                [r["key"], r["unit"] or ""] + [formatting.format_number(v) for v in r["values"]]
                for r in result["rows"]
            ]
            csv_text = formatting.render_csv(headers, rows)
            return Response(
                csv_text,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=compare.csv"},
            )
        if fmt == "params-csv" and param_result is not None:
            headers = ["key"] + [rm["name"] or rm["id"] for rm in param_result["runs"]]
            rows = [
                [r["key"]] + [v if v is not None else "" for v in r["values"]]
                for r in param_result["rows"]
            ]
            csv_text = formatting.render_csv(headers, rows)
            return Response(
                csv_text,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=compare_params.csv"},
            )

        return render_template(
            "compare.html",
            error=None,
            result=result,
            param_result=param_result,
            stat_globs=", ".join(stat_globs),
            param_globs=", ".join(param_globs),
            base_qs=base_qs,
        )

    return app
