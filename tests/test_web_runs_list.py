import pytest

from m5mgr import cli, config


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("M5MGR_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _import_synthetic(capsys, tmp_path, run_name, *, stat_key, stat_value):
    m5out = tmp_path / run_name
    m5out.mkdir()
    (m5out / "stats.txt").write_text(
        "---------- Begin Simulation Statistics ----------\n"
        f"{stat_key}                      {stat_value}\n"
        "----------   End Simulation Statistics   ----------\n"
    )
    rc = cli.main(["import", str(m5out), "--name", run_name, "--id-only"])
    assert rc == 0
    return capsys.readouterr().out.strip()


@pytest.fixture
def client(home):
    from m5mgr.web.app import create_app

    app = create_app(str(config.db_path()))
    app.testing = True
    return app.test_client()


def test_runs_list_default_match_all_ands_filters(capsys, home, tmp_path, client):
    _import_synthetic(capsys, tmp_path, "run-a", stat_key="statA", stat_value=1.0)
    _import_synthetic(capsys, tmp_path, "run-b", stat_key="statB", stat_value=1.0)

    # A single text box carrying two comma-separated filter expressions.
    resp = client.get("/runs", query_string={"stat": "statA>=1.0, statB>=1.0"})
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "run-a" not in body
    assert "run-b" not in body
    assert "No runs found." in body


def test_runs_list_match_any_ors_filters(capsys, home, tmp_path, client):
    _import_synthetic(capsys, tmp_path, "run-a", stat_key="statA", stat_value=1.0)
    _import_synthetic(capsys, tmp_path, "run-b", stat_key="statB", stat_value=1.0)
    _import_synthetic(capsys, tmp_path, "run-c", stat_key="statC", stat_value=1.0)

    resp = client.get("/runs", query_string={"stat": "statA>=1.0, statB>=1.0", "match": "any"})
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "run-a" in body
    assert "run-b" in body
    assert "run-c" not in body
