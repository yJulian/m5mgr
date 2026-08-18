import pytest

from m5mgr import config


def test_scope_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("M5MGR_SCOPE", raising=False)
    assert config.scope() == "default"


def test_scope_reads_env_var(monkeypatch):
    monkeypatch.setenv("M5MGR_SCOPE", "project-a")
    assert config.scope() == "project-a"


def test_scope_rejects_invalid_characters(monkeypatch):
    monkeypatch.setenv("M5MGR_SCOPE", "../escape")
    with pytest.raises(config.ConfigError):
        config.scope()


def test_scope_rejects_path_separator(monkeypatch):
    monkeypatch.setenv("M5MGR_SCOPE", "a/b")
    with pytest.raises(config.ConfigError):
        config.scope()


def test_different_scopes_get_different_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("M5MGR_HOME", str(tmp_path))

    monkeypatch.setenv("M5MGR_SCOPE", "scope-a")
    db_a = config.db_path()
    runs_a = config.runs_dir()

    monkeypatch.setenv("M5MGR_SCOPE", "scope-b")
    db_b = config.db_path()
    runs_b = config.runs_dir()

    assert db_a != db_b
    assert runs_a != runs_b
    assert db_a.parent.name == "scope-a"
    assert db_b.parent.name == "scope-b"


def test_unset_scope_and_unset_home_still_work(tmp_path, monkeypatch):
    monkeypatch.setenv("M5MGR_HOME", str(tmp_path))
    monkeypatch.delenv("M5MGR_SCOPE", raising=False)
    assert config.db_path() == tmp_path / "default" / "m5mgr.db"
