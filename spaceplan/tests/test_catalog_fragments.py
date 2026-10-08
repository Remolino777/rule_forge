"""Residential catalog split into module fragments (refactor tanda 1).

The merged fragments must be identical to the pre-split residential_catalog.json, kept as reference
until tanda 4.
"""

import copy
import json
from pathlib import Path

import pytest

from spaceplan.core.lib.catalog import (
    FRAGMENT_CHECKS,
    CatalogError,
    catalog_errors,
    load_catalog,
    load_catalog_data,
    merge_fragments,
)
from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_resource_json

CATALOG_DIR = Path(__file__).resolve().parents[1] / "spaceplan" / "data" / "catalog"
FRAGMENTS = CATALOG_DIR / "fragments"


@pytest.fixture(scope="module")
def original():
    return load_resource_json("spaceplan", "data", "catalog", "residential_catalog.json")


@pytest.fixture(scope="module")
def index():
    return json.loads((FRAGMENTS / "index.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fragments(index):
    return {n: json.loads((FRAGMENTS / f"{n}.json").read_text(encoding="utf-8")) for n in index["fragments"]}


def test_merged_fragments_equal_the_original_catalog(original):
    merged = load_catalog_data()
    assert merged == original
    assert list(merged) == list(original)
    assert json.dumps(merged, ensure_ascii=False) == json.dumps(original, ensure_ascii=False)


def test_loaded_catalog_hash_is_unchanged(original):
    catalog = load_catalog()
    assert catalog.sha256 == sha256_of(original)
    assert catalog.version == original["catalog_version"]


def test_every_key_has_exactly_one_owner(index, fragments, original):
    owners = [k for f in fragments.values() for k in f["entries"]]
    assert sorted(owners) == sorted(original)
    assert len(owners) == len(set(owners))
    assert index["key_order"] == list(original)


def test_fragment_files_match_index(index, fragments):
    on_disk = {p.stem for p in FRAGMENTS.glob("*.json")} - {"index"}
    assert on_disk == set(index["fragments"])
    assert all(f["fragment"] == name for name, f in fragments.items())
    assert set(FRAGMENT_CHECKS) <= set(index["fragments"])


def test_household_catalog_stays_separate(index):
    household = load_resource_json("spaceplan", "data", "catalog", "household_catalog.json")
    assert index["separate_catalogs"] == {"household": "household_catalog.json"}
    assert not (set(household) & set(load_catalog_data())) - {"default_source"}


def test_load_from_index_on_disk_equals_default():
    assert load_catalog(FRAGMENTS / "index.json").data == load_catalog().data


def test_load_single_file_still_supported(original):
    assert load_catalog(CATALOG_DIR / "residential_catalog.json").data == original


def test_duplicate_key_across_fragments_is_rejected(index, fragments):
    bad = copy.deepcopy(fragments)
    bad["viz"]["entries"]["zones"] = []
    with pytest.raises(CatalogError, match="more than one fragment"):
        merge_fragments(index, bad)


def test_missing_key_is_rejected(index, fragments):
    bad = copy.deepcopy(fragments)
    del bad["cost"]["entries"]["cost_index"]
    with pytest.raises(CatalogError, match="key_order"):
        merge_fragments(index, bad)


def test_mislabelled_fragment_is_rejected(index, fragments):
    bad = copy.deepcopy(fragments)
    bad["cost"]["fragment"] = "zoning"
    with pytest.raises(CatalogError, match="declares fragment"):
        merge_fragments(index, bad)


@pytest.mark.parametrize("name", list(FRAGMENT_CHECKS))
def test_each_fragment_check_passes_on_the_catalog(name):
    data = load_catalog_data()
    types = {t["space_type"]: t for t in data["space_types"]}
    assert FRAGMENT_CHECKS[name](data, types) == []


@pytest.mark.parametrize("fragment, mutate, message", [
    ("core", lambda d: d["space_types"][0]["area"].update(min=10**6), "min <= target <= max"),
    ("household", lambda d: d["typologies"][0]["spaces"][0].update(space_type="nope"), "unknown space type"),
    ("cost", lambda d: d["cost_index"].update(default_model="carbon"), "default_model"),
    ("areas", lambda d: d["area_analysis"].update(garden_min_fraction_of_lot=1.5), "garden_min_fraction"),
])
def test_semantic_errors_are_reported_by_their_fragment(fragment, mutate, message):
    data = copy.deepcopy(load_catalog_data())
    mutate(data)
    types = {t["space_type"]: t for t in data["space_types"]}
    assert any(message in e for e in FRAGMENT_CHECKS[fragment](data, types))
    assert any(message in e for e in catalog_errors(data))
