import json

import pytest

from conftest import FIXTURE_DIRS
from m5mgr.config_flattener import flatten_config


def _reference_leaf_count(obj) -> int:
    """Independent second implementation used to cross-check flatten_config's row count."""
    if isinstance(obj, dict):
        return sum(_reference_leaf_count(v) for v in obj.values())
    if isinstance(obj, list):
        return 1 if not obj else sum(_reference_leaf_count(v) for v in obj)
    return 1


@pytest.fixture
def config_dict():
    with open(FIXTURE_DIRS["single"] / "config.json") as f:
        return json.load(f)


def test_leaf_count_matches_independent_reference(config_dict):
    rows = flatten_config(config_dict)
    assert len(rows) == _reference_leaf_count(config_dict)
    assert len(rows) > 1000  # sanity: this config.json is large


def test_scalar_list_flattening(config_dict):
    rows = {r.key: r for r in flatten_config(config_dict)}
    assert rows["system.mem_ranges[0]"].value_text == "2147483648:2415919104"
    assert rows["system.mem_ranges[0]"].value_type == "str"


def test_list_of_dicts_flattening(config_dict):
    rows = {r.key: r for r in flatten_config(config_dict)}
    assert "system.ruby.network.int_links[0].latency" in rows
    assert rows["system.ruby.network.int_links[0].latency"].value_type in ("int", "float")


def test_bool_and_null_classification(config_dict):
    rows = {r.key: r for r in flatten_config(config_dict)}
    full_system = rows["full_system"]
    assert full_system.value_type == "bool"
    assert full_system.value_num == 1.0
    assert full_system.value_text == "true"
