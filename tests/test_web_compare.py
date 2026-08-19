import json

import pytest

from m5mgr import cli, config


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("M5MGR_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _make_m5out(tmp_path, dirname, *, sim_seconds, num_threads):
    m5out = tmp_path / dirname
    m5out.mkdir()
    (m5out / "stats.txt").write_text(
        "---------- Begin Simulation Statistics ----------\n"
        f"simSeconds                      {sim_seconds}                       # Number of seconds simulated\n"
        "hostSeconds                      1.23                       # Real time elapsed on the host\n"
        "----------   End Simulation Statistics   ----------\n"
    )
    (m5out / "config.json").write_text(
        json.dumps({"system": {"cpu": {"numThreads": num_threads, "clock": 1000}}})
    )
    return m5out


def _import(capsys, tmp_path, dirname, run_name, **kwargs):
    m5out = _make_m5out(tmp_path, dirname, **kwargs)
    rc = cli.main(["import", str(m5out), "--name", run_name, "--id-only"])
    assert rc == 0
    return capsys.readouterr().out.strip()  # the run id


@pytest.fixture
def client(home):
    from m5mgr.web.app import create_app

    app = create_app(str(config.db_path()))
    app.testing = True
    return app.test_client()


def test_compare_requires_two_runs(client):
    resp = client.get("/compare", query_string={"run": "only-one"})
    assert b"Select at least 2 runs" in resp.data


def test_compare_stats_filter(capsys, home, tmp_path, client):
    id_single = _import(capsys, tmp_path, "m5out_single", "run-single", sim_seconds="0.0047", num_threads=1)
    id_k37 = _import(capsys, tmp_path, "m5out_k37", "run-k37", sim_seconds="0.0094", num_threads=1)

    resp = client.get(
        "/compare",
        query_string=[("run", id_single), ("run", id_k37), ("stat", "simSeconds")],
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "simSeconds" in body
    assert "run-single" in body
    assert "run-k37" in body
    # No baseline selected yet -> plain values, no percent differences.
    assert "pct-diff" not in body
    # A stat filter that doesn't match anything else should exclude it.
    assert "hostSeconds" not in body
    # Column headers show the run name alone, never "name (id)".
    assert f"({id_single})" not in body
    assert f"({id_k37})" not in body


def test_compare_baseline_click_shows_pct_diff_on_other_columns(capsys, home, tmp_path, client):
    id_single = _import(capsys, tmp_path, "m5out_single", "run-single", sim_seconds="0.0047", num_threads=1)
    id_k37 = _import(capsys, tmp_path, "m5out_k37", "run-k37", sim_seconds="0.0094", num_threads=1)

    resp = client.get(
        "/compare",
        query_string=[("run", id_single), ("run", id_k37), ("stat", "simSeconds"), ("baseline", id_single)],
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    # run-k37 (0.0094) is a +100% diff from the run-single (0.0047) baseline.
    assert "(+100.0%)" in body
    # The baseline column itself never gets a percent badge next to its value.
    assert "(+0.0%)" not in body
    assert 'class="baseline-col"' in body or "baseline-col" in body
    assert "clear baseline" in body


def test_compare_invalid_baseline_ref_is_ignored(capsys, home, tmp_path, client):
    id_single = _import(capsys, tmp_path, "m5out_single", "run-single", sim_seconds="0.0047", num_threads=1)
    id_k37 = _import(capsys, tmp_path, "m5out_k37", "run-k37", sim_seconds="0.0094", num_threads=1)

    resp = client.get(
        "/compare",
        query_string=[("run", id_single), ("run", id_k37), ("stat", "simSeconds"), ("baseline", "not-a-real-run-id")],
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "pct-diff" not in body
    assert "clear baseline" not in body


def test_compare_stat_glob_comma_separated_is_ored(capsys, home, tmp_path, client):
    id_single = _import(capsys, tmp_path, "m5out_single", "run-single", sim_seconds="0.0047", num_threads=1)
    id_k37 = _import(capsys, tmp_path, "m5out_k37", "run-k37", sim_seconds="0.0094", num_threads=1)

    # One text box, two comma-separated globs -> rows matching either show up.
    resp = client.get(
        "/compare",
        query_string=[("run", id_single), ("run", id_k37), ("stat", "simSeconds, hostSeconds")],
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "simSeconds" in body
    assert "hostSeconds" in body


def test_compare_param_filter_shows_params_section(capsys, home, tmp_path, client):
    id_single = _import(capsys, tmp_path, "m5out_single", "run-single", sim_seconds="0.0047", num_threads=1)
    id_k37 = _import(capsys, tmp_path, "m5out_k37", "run-k37", sim_seconds="0.0094", num_threads=4)

    resp = client.get(
        "/compare",
        query_string=[("run", id_single), ("run", id_k37), ("param", "system.cpu.numThreads")],
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Params" in body
    assert "system.cpu.numThreads" in body
    # --param without --stat mirrors the CLI: stats section is suppressed.
    assert "<h2>Stats</h2>" not in body
    # A param filter that doesn't match should exclude that key.
    assert "system.cpu.clock" not in body


def test_compare_params_csv_download(capsys, home, tmp_path, client):
    id_single = _import(capsys, tmp_path, "m5out_single", "run-single", sim_seconds="0.0047", num_threads=1)
    id_k37 = _import(capsys, tmp_path, "m5out_k37", "run-k37", sim_seconds="0.0094", num_threads=4)

    resp = client.get(
        "/compare",
        query_string=[
            ("run", id_single),
            ("run", id_k37),
            ("param", "system.cpu.numThreads"),
            ("format", "params-csv"),
        ],
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment; filename=compare_params.csv" in resp.headers["Content-Disposition"]
    assert "system.cpu.numThreads" in resp.data.decode()
