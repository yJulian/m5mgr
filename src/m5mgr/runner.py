"""Builds and executes the gem5 subprocess invocation.

m5mgr owns the -d (output dir) flag itself so it always knows where the
resulting m5out directory is; everything else passed after `--` on the
command line goes to gem5 completely unmodified.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

_FORBIDDEN_FLAGS = {"-d", "--outdir"}


class PassthroughArgError(ValueError):
    pass


def check_passthrough_args(args: list[str]) -> None:
    for a in args:
        if a in _FORBIDDEN_FLAGS:
            raise PassthroughArgError(
                f"gem5 args must not include {a!r} - m5mgr controls the m5out directory "
                "itself via its own `run --outdir` flag, not gem5's -d/--outdir."
            )


def build_gem5_argv(gem5_bin: str, staging_dir: str, passthrough_args: list[str]) -> list[str]:
    """gem5's own arg parser requires global options like -d to precede the
    script/positional args, so -d is inserted immediately after the
    executable rather than anywhere within passthrough_args."""
    check_passthrough_args(passthrough_args)
    return [gem5_bin, "-d", staging_dir, *passthrough_args]


def run_gem5(
    gem5_bin: str,
    staging_dir: str,
    passthrough_args: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, float]:
    argv = build_gem5_argv(gem5_bin, staging_dir, passthrough_args)
    start = time.monotonic()
    with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
        proc = subprocess.run(argv, stdout=out, stderr=err)
    duration = time.monotonic() - start
    return proc.returncode, duration
