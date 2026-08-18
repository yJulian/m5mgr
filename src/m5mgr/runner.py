"""Builds and executes the gem5 subprocess invocation.

m5mgr owns the -d (output dir) flag itself so it always knows where the
resulting m5out directory is; everything else passed after `--` on the
command line goes to gem5 completely unmodified.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO

_FORBIDDEN_FLAGS = {"-d", "--outdir"}
_CHUNK_SIZE = 4096


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


def _write_console(console: IO, chunk: bytes) -> None:
    buffer = getattr(console, "buffer", None)
    if buffer is not None:
        buffer.write(chunk)
    else:
        console.write(chunk.decode(errors="replace"))
    console.flush()


def _pump(src: IO[bytes], console: IO, log_path: Path) -> None:
    """Copy src (gem5's stdout or stderr) to both the live console and a log file."""
    with open(log_path, "wb") as log_file:
        while True:
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            _write_console(console, chunk)
            log_file.write(chunk)
    src.close()


def run_gem5(
    gem5_bin: str,
    staging_dir: str,
    passthrough_args: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, float]:
    """Runs gem5, streaming its stdout/stderr live to the console while also
    saving each to its own log file in staging_dir."""
    argv = build_gem5_argv(gem5_bin, staging_dir, passthrough_args)
    start = time.monotonic()

    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t_out = threading.Thread(target=_pump, args=(proc.stdout, sys.stdout, stdout_path))
    t_err = threading.Thread(target=_pump, args=(proc.stderr, sys.stderr, stderr_path))
    t_out.start()
    t_err.start()
    t_out.join()
    t_err.join()
    returncode = proc.wait()

    duration = time.monotonic() - start
    return returncode, duration
