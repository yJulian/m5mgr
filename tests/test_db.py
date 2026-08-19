import pytest

from m5mgr import db
from m5mgr.config_flattener import ParamRow
from m5mgr.stats_parser import Dump, StatRow


def _make_run(rid, name, created_at="2026-08-18T00:00:00+00:00"):
    return db.RunRecord(
        id=rid,
        name=name,
        created_at=created_at,
        source="import",
        status="completed",
        m5out_dir=f"/tmp/{rid}/m5out",
        n_dumps=1,
    )


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_insert_and_get_run(conn):
    run = _make_run("RUN1", "myrun")
    db.insert_run(conn, run)
    row = db.get_run(conn, "RUN1")
    assert row["name"] == "myrun"
    assert row["status"] == "completed"


def test_insert_dumps_stats_params(conn):
    run = _make_run("RUN2", "withstats")
    db.insert_run(conn, run)

    dump = Dump(index=0, line_start=1, line_end=5, complete=True)
    dump.rows.append(StatRow(key="simSeconds", value=1.5, value_text="1.5", unit="Second"))
    db.insert_dumps(conn, "RUN2", [dump])
    db.insert_stats(conn, "RUN2", [dump])
    db.insert_params(conn, "RUN2", [ParamRow(key="system.cpu.numThreads", value_text="4", value_num=4.0, value_type="int")])

    stats = db.get_stats(conn, "RUN2", 0)
    assert len(stats) == 1
    assert stats[0]["key"] == "simSeconds"

    params = db.get_params(conn, "RUN2")
    assert len(params) == 1
    assert params[0]["value_num"] == 4.0


def test_resolve_ref_by_exact_id(conn):
    db.insert_run(conn, _make_run("EXACTID", "name-a"))
    row = db.resolve_ref(conn, "EXACTID")
    assert row["id"] == "EXACTID"


def test_resolve_ref_by_unique_prefix(conn):
    db.insert_run(conn, _make_run("PREFIX123", "name-b"))
    row = db.resolve_ref(conn, "PREFIX1")
    assert row["id"] == "PREFIX123"


def test_resolve_ref_by_unique_name(conn):
    db.insert_run(conn, _make_run("IDX", "unique-name"))
    row = db.resolve_ref(conn, "unique-name")
    assert row["id"] == "IDX"


def test_resolve_ref_ambiguous_name_raises(conn):
    db.insert_run(conn, _make_run("IDA", "dupe", created_at="2026-08-18T00:00:00+00:00"))
    db.insert_run(conn, _make_run("IDB", "dupe", created_at="2026-08-18T01:00:00+00:00"))
    with pytest.raises(db.AmbiguousRefError) as exc_info:
        db.resolve_ref(conn, "dupe")
    matched_ids = {m["id"] for m in exc_info.value.matches}
    assert matched_ids == {"IDA", "IDB"}


def test_resolve_ref_not_found_raises(conn):
    with pytest.raises(db.RunNotFoundError):
        db.resolve_ref(conn, "nope")


def _run_with_stat(conn, rid, name, *, key, value):
    db.insert_run(conn, _make_run(rid, name))
    dump = Dump(index=0, line_start=1, line_end=2, complete=True)
    dump.rows.append(StatRow(key=key, value=value, value_text=str(value)))
    db.insert_dumps(conn, rid, [dump])
    db.insert_stats(conn, rid, [dump])


def test_list_runs_match_all_requires_every_filter(conn):
    _run_with_stat(conn, "A", "run-a", key="statA", value=1.0)
    _run_with_stat(conn, "B", "run-b", key="statB", value=1.0)
    db.insert_run(conn, _make_run("C", "run-c"))  # matches neither

    filters = (("statA", ">=", 1.0), ("statB", ">=", 1.0))
    rows = db.list_runs(conn, stat_filters=filters, match="all")
    assert [r["id"] for r in rows] == []  # no run has both stats


def test_list_runs_match_any_matches_either_filter(conn):
    _run_with_stat(conn, "A", "run-a", key="statA", value=1.0)
    _run_with_stat(conn, "B", "run-b", key="statB", value=1.0)
    db.insert_run(conn, _make_run("C", "run-c"))  # matches neither

    filters = (("statA", ">=", 1.0), ("statB", ">=", 1.0))
    rows = db.list_runs(conn, stat_filters=filters, match="any")
    assert {r["id"] for r in rows} == {"A", "B"}


def test_list_runs_invalid_match_raises(conn):
    with pytest.raises(ValueError):
        db.list_runs(conn, match="xor")


def test_delete_run_cascades(conn):
    run = _make_run("DELME", "todelete")
    db.insert_run(conn, run)
    dump = Dump(index=0, line_start=1, line_end=2, complete=True)
    dump.rows.append(StatRow(key="k", value=1.0, value_text="1"))
    db.insert_dumps(conn, "DELME", [dump])
    db.insert_stats(conn, "DELME", [dump])

    db.delete_run(conn, "DELME")

    assert db.get_run(conn, "DELME") is None
    assert conn.execute("SELECT COUNT(*) FROM dumps WHERE run_id='DELME'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM stats WHERE run_id='DELME'").fetchone()[0] == 0
