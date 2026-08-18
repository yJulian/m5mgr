from pathlib import Path

import pytest

from m5mgr import runner

FAKE_GEM5 = Path(__file__).parent / "fixtures" / "fake_gem5.sh"


def test_build_gem5_argv_inserts_d_immediately_after_binary():
    argv = runner.build_gem5_argv("/usr/bin/gem5.opt", "/tmp/out", ["-re", "script.py", "--opt=1"])
    assert argv == ["/usr/bin/gem5.opt", "-d", "/tmp/out", "-re", "script.py", "--opt=1"]


def test_build_gem5_argv_rejects_dash_d_in_passthrough():
    with pytest.raises(runner.PassthroughArgError):
        runner.build_gem5_argv("/usr/bin/gem5.opt", "/tmp/out", ["-d", "/other"])


def test_build_gem5_argv_rejects_outdir_long_flag():
    with pytest.raises(runner.PassthroughArgError):
        runner.build_gem5_argv("/usr/bin/gem5.opt", "/tmp/out", ["--outdir", "/other"])


def test_run_gem5_against_fake_binary(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()

    exit_code, duration = runner.run_gem5(
        str(FAKE_GEM5),
        str(staging),
        ["-re", "script.py"],
        stdout_path=tmp_path / "out.log",
        stderr_path=tmp_path / "err.log",
    )

    assert exit_code == 0
    assert duration >= 0
    assert (staging / "stats.txt").exists()
    assert (staging / "config.json").exists()


def test_run_gem5_records_argv(tmp_path, monkeypatch):
    argv_file = tmp_path / "argv.txt"
    monkeypatch.setenv("FAKE_GEM5_ARGV_FILE", str(argv_file))

    staging = tmp_path / "staging2"
    staging.mkdir()
    runner.run_gem5(
        str(FAKE_GEM5),
        str(staging),
        ["-re", "script.py", "--flag"],
        stdout_path=tmp_path / "o.log",
        stderr_path=tmp_path / "e.log",
    )

    recorded = argv_file.read_text().splitlines()
    assert recorded == ["-d", str(staging), "-re", "script.py", "--flag"]


def test_run_gem5_propagates_nonzero_exit_code(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_GEM5_EXIT_CODE", "3")
    staging = tmp_path / "staging3"
    staging.mkdir()

    exit_code, _ = runner.run_gem5(
        str(FAKE_GEM5),
        str(staging),
        ["-re", "script.py"],
        stdout_path=tmp_path / "o.log",
        stderr_path=tmp_path / "e.log",
    )

    assert exit_code == 3
