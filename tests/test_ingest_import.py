import pytest

from conftest import FIXTURE_DIRS
from m5mgr import config, db, ingest


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("M5MGR_HOME", str(tmp_path / "home"))
    c = db.connect(config.db_path())
    yield c
    c.close()


@pytest.mark.parametrize("fixture_name", FIXTURE_DIRS.keys())
def test_ingest_existing_dir(conn, fixture_name):
    record = ingest.ingest_existing_dir(conn, FIXTURE_DIRS[fixture_name], name=f"test-{fixture_name}")

    assert record.source == "import"
    assert record.status == "completed"
    assert record.n_dumps >= 1

    row = db.get_run(conn, record.id)
    assert row["name"] == f"test-{fixture_name}"

    stats = conn.execute("SELECT COUNT(*) FROM stats WHERE run_id = ?", (record.id,)).fetchone()[0]
    assert stats > 0

    params = conn.execute("SELECT COUNT(*) FROM params WHERE run_id = ?", (record.id,)).fetchone()[0]
    assert params > 0


def test_ingest_copies_files_not_moves_by_default(conn, tmp_path):
    ingest.ingest_existing_dir(conn, FIXTURE_DIRS["single"], name="copy-test")
    assert (FIXTURE_DIRS["single"] / "stats.txt").exists()  # original untouched
