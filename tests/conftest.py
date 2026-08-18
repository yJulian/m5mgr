from pathlib import Path

import pytest

INPUT_DIR = Path(__file__).parent.parent / "input"

FIXTURE_DIRS = {
    "single": INPUT_DIR / "m5out_rtl3_32x32_single",
    "k37_32x32": INPUT_DIR / "m5out_rtl3_32x32_K37",
    "k37_8x8": INPUT_DIR / "m5out_rtl3_8x8_K37",
    "k21_orig": INPUT_DIR / "m5out_rtl3_8x8_K21_orig",
}


@pytest.fixture
def m5mgr_home(tmp_path, monkeypatch):
    home = tmp_path / "m5mgr-home"
    monkeypatch.setenv("M5MGR_HOME", str(home))
    return home
