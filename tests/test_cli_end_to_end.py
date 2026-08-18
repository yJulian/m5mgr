import pytest

from conftest import FIXTURE_DIRS
from m5mgr import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("M5MGR_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _import(capsys, home, fixture_name, run_name):
    rc = cli.main(["import", str(FIXTURE_DIRS[fixture_name]), "--name", run_name, "--id-only"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    return out  # the run id


def test_import_list_show_compare(capsys, home):
    id_single = _import(capsys, home, "single", "run-single")
    id_k37 = _import(capsys, home, "k37_32x32", "run-k37")
    _import(capsys, home, "k21_orig", "run-k21")
    _import(capsys, home, "k37_8x8", "run-k37-8x8")

    rc = cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "run-single" in out
    assert "run-k37" in out
    assert "run-k21" in out
    assert "run-k37-8x8" in out

    rc = cli.main(["show", id_single, "--stat", "simSeconds"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "simSeconds" in out
    assert "0.0047" in out

    rc = cli.main(["compare", id_single, id_k37, "--stat", "simSeconds"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "simSeconds" in out
    assert "run-single" in out
    assert "run-k37" in out


def test_show_ambiguous_name_errors(capsys, home):
    _import(capsys, home, "single", "dup")
    _import(capsys, home, "k21_orig", "dup")

    rc = cli.main(["show", "dup"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ambiguous" in err.lower() or "Ambiguous" in err


def test_all_dumps_flag_shows_multiple_dumps(capsys, home):
    id_k37 = _import(capsys, home, "k37_32x32", "multi-dump-run")
    rc = cli.main(["show", id_k37, "--all-dumps", "--stat", "simSeconds"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dump 0" in out
    assert "Dump 1" in out


def test_scopes_isolate_runs(capsys, home, monkeypatch):
    monkeypatch.setenv("M5MGR_SCOPE", "project-a")
    id_a = _import(capsys, home, "single", "run-in-a")

    monkeypatch.setenv("M5MGR_SCOPE", "project-b")
    id_b = _import(capsys, home, "k21_orig", "run-in-b")

    rc = cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Scope: project-b" in out
    assert "run-in-b" in out
    assert "run-in-a" not in out

    # A run id from another scope must not resolve here.
    rc = cli.main(["show", id_a])
    assert rc == 2
    capsys.readouterr()

    monkeypatch.setenv("M5MGR_SCOPE", "project-a")
    rc = cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Scope: project-a" in out
    assert "run-in-a" in out
    assert "run-in-b" not in out

    rc = cli.main(["show", id_a, "--stat", "simSeconds"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "simSeconds" in out

    # DB and run store actually live in separate scope subdirectories.
    assert (home / "project-a" / "m5mgr.db").exists()
    assert (home / "project-b" / "m5mgr.db").exists()
    assert (home / "project-a" / "runs" / id_a).is_dir()
    assert (home / "project-b" / "runs" / id_b).is_dir()


def test_default_scope_used_when_unset(capsys, home, monkeypatch):
    monkeypatch.delenv("M5MGR_SCOPE", raising=False)
    _import(capsys, home, "single", "default-scope-run")
    assert (home / "default" / "m5mgr.db").exists()
