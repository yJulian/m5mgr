import pytest

from conftest import FIXTURE_DIRS
from m5mgr.stats_parser import parse_stats_file

EXPECTED_DUMP_COUNTS = {
    "single": 1,
    "k21_orig": 1,
    "k37_32x32": 2,
    "k37_8x8": 2,
}


@pytest.mark.parametrize("fixture_name", EXPECTED_DUMP_COUNTS.keys())
def test_dump_counts(fixture_name):
    dumps = parse_stats_file(FIXTURE_DIRS[fixture_name] / "stats.txt")
    assert len(dumps) == EXPECTED_DUMP_COUNTS[fixture_name]


def test_scalar_value():
    dumps = parse_stats_file(FIXTURE_DIRS["single"] / "stats.txt")
    rows = {r.key: r for r in dumps[0].rows}
    assert rows["simSeconds"].value == pytest.approx(0.004700)
    assert rows["simSeconds"].unit == "Second"
    assert "seconds simulated" in rows["simSeconds"].description


def test_percentage_columns():
    dumps = parse_stats_file(FIXTURE_DIRS["single"] / "stats.txt")
    rows = {r.key: r for r in dumps[0].rows}
    row = rows["system.cpu.issuedInstType_0::IntAlu"]
    assert row.value == 4398301
    assert row.percent == pytest.approx(89.55, abs=0.01)
    assert row.unit == "Count"


def test_nan_value_does_not_crash():
    dumps = parse_stats_file(FIXTURE_DIRS["single"] / "stats.txt")
    rows = {r.key: r for r in dumps[0].rows}
    row = rows["system.mem_ctrls.dram.writeRowHitRate"]
    assert row.value is None
    assert row.value_text == "nan"
    assert row.unit == "Ratio"


def test_pipe_vector_expands_to_indexed_subrows():
    dumps = parse_stats_file(FIXTURE_DIRS["single"] / "stats.txt")
    rows = {r.key: r for r in dumps[0].rows}
    subrows = [rows[f"system.ruby.m_outstandReqHistSeqr::{i}"] for i in range(10)]
    assert subrows[0].value == 0
    assert subrows[1].value == 743750
    assert subrows[-1].cum_percent == pytest.approx(100.00, abs=0.01)


def test_named_histogram_buckets_are_plain_keys():
    dumps = parse_stats_file(FIXTURE_DIRS["single"] / "stats.txt")
    rows = {r.key: r for r in dumps[0].rows}
    row = rows["system.mem_ctrls.dram.bytesPerActivate::0-127"]
    assert row.value == 3
    assert row.percent == pytest.approx(7.89, abs=0.01)


def test_multi_dump_file_has_distinct_dumps():
    dumps = parse_stats_file(FIXTURE_DIRS["k37_32x32"] / "stats.txt")
    assert dumps[0].index == 0
    assert dumps[1].index == 1
    assert dumps[0].line_start < dumps[0].line_end < dumps[1].line_start
    assert all(d.complete for d in dumps)
