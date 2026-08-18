"""Environment/path resolution shared by the CLI and the web app."""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_SCOPE = "default"
_SCOPE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ConfigError(RuntimeError):
    pass


def gem5_bin() -> str:
    value = os.environ.get("GEM5_BIN")
    if not value:
        raise ConfigError(
            "GEM5_BIN is not set. Point it at your gem5 executable, e.g.\n"
            "  export GEM5_BIN=/path/to/gem5.opt"
        )
    path = Path(value)
    if not path.exists():
        raise ConfigError(f"GEM5_BIN points at a nonexistent path: {value}")
    return str(path)


def scope() -> str:
    """The active m5mgr scope (M5MGR_SCOPE, default 'default').

    Scopes keep multiple projects' runs (and their ids/names) fully separate
    within the same M5MGR_HOME - each scope gets its own db and run store, so
    unrelated projects never see or collide with each other's runs.
    """
    value = os.environ.get("M5MGR_SCOPE") or DEFAULT_SCOPE
    if not _SCOPE_RE.match(value):
        raise ConfigError(
            f"M5MGR_SCOPE={value!r} is invalid - only letters, digits, '_', '-' and '.' are allowed."
        )
    return value


def m5mgr_home() -> Path:
    value = os.environ.get("M5MGR_HOME")
    home = Path(value).expanduser() if value else Path.home() / ".local" / "share" / "m5mgr"
    home.mkdir(parents=True, exist_ok=True)
    return home


def scope_dir() -> Path:
    d = m5mgr_home() / scope()
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return scope_dir() / "m5mgr.db"


def runs_dir() -> Path:
    d = scope_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_dir(run_id: str) -> Path:
    return runs_dir() / run_id
