"""Residential catalog split into module fragments (refactor tanda 1).

The merged fragments must be identical to the pre-split residential_catalog.json. Tanda 1 compared them with
the file itself; tanda 4 removed the file and keeps its SHA-256 (canonical JSON) and its key order as the
reference, so the guarantee stays.
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

CATALOG_DIR = Path(__file__).resolve().parents[2] / "spaceplan" / "data" / "catalog"
FRAGMENTS = CATALOG_DIR / "fragments"


# SHA-256 (canonical JSON) of the pre-split residential_catalog.json (catalog 0.11.0), frozen when the file was
# removed (refactor tanda 4, 2026-10-09); tanda 1 proved the merged fragments identical to it:
#   0.11.0  450545922efa135daa6dbbaa4be83de38705801976a09bf632285072631b034e
# Catalog 0.12.0 (2026-10-09, step 6.7a area logic, client-approved): stair area per floor from the CRC stair
# geometry of S1.1 (37.5 / 44 / 53 sq ft instead of 40 / 60 / 90) and the lot-minimum typology h1_basic. Any other
# change to the fragments must bump the version and the hash here.
#   0.12.0  17ca8654495722031b6a01da2c3a9affd868f10c2e67ad7edff397eb3996f6b9
# Catalog 0.13.0 (2026-10-10, step 9a, client-approved): rule vertical_schemes.ground_balance (balanced split between
# floors: family room, study, flex room, storage go up until the ground floor fits the design footprint).
REFERENCE_SHA256 = "7825fa60c315e6d1b0cc933cbe19020a1ec96f0455794fd37f2d0e97e8b626a6"
REFERENCE_VERSION = "0.13.0"


@pytest.fixture(scope="module")
def index():
    return json.loads((FRAGMENTS / "index.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fragments(index):
    return {n: json.loads((FRAGMENTS / f"{n}.json").read_text(encoding="utf-8")) for n in index["fragments"]}


def test_merged_fragments_equal_the_pre_split_catalog(index):
    merged = load_catalog_data()
    assert sha256_of(merged) == REFERENCE_SHA256
    assert list(merged) == index["key_order"]


def test_loaded_catalog_hash_is_unchanged():
    catalog = load_catalog()
    assert catalog.sha256 == REFERENCE_SHA256
    assert catalog.version == REFERENCE_VERSION


def test_pre_split_file_is_gone():
    assert not (CATALOG_DIR / "residential_catalog.json").exists()


def test_every_key_has_exactly_one_owner(index, fragments):
    owners = [k for f in fragments.values() for k in f["entries"]]
    assert sorted(owners) == sorted(index["key_order"])
    assert len(owners) == len(set(owners))


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


def test_load_single_file_still_supported(tmp_path):
    single = tmp_path / "catalog.json"
    single.write_text(json.dumps(load_catalog_data(), ensure_ascii=False), encoding="utf-8")
    loaded = load_catalog(single)
    assert loaded.data == load_catalog_data() and loaded.sha256 == REFERENCE_SHA256


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
