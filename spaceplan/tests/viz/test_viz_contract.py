"""viz module from contracts (refactor tanda 4): figures drawn from the fixtures, no domain computation."""

from pathlib import Path

import pytest
from conftest import load_fixture

from spaceplan.core.lib.contracts import ContractValidationError
from spaceplan.modules.viz.main.run_viz import draw_capacity, draw_site, draw_zoning, package_view

HOUSE = "interior_50x100"


def _contracts(name=HOUSE):
    return (load_fixture("lot_capacity", name), load_fixture("site_plan", name), load_fixture("zoning_scheme", name))


def test_package_view_reads_the_blocks_as_they_are():
    lot, site, zoning = _contracts()
    view = package_view(lot, site, zoning)
    assert view["capacity"] is not None and view["capacity"] == lot["capacity"]
    assert view["site_partition"] == site["site_partition"] and view["zoning"] == zoning["zoning"]
    assert view["meta"] == {"brief_id": "interior-50x100", "dwelling_type": "house",
                            "realization_strategy": zoning["realization_strategy"]}


def test_house_figures_from_contracts(tmp_path):
    lot, site, zoning = _contracts()
    figures = [draw_capacity(lot, tmp_path / "cap.png"), draw_site(lot, site, tmp_path / "site.png"),
               draw_zoning(zoning, tmp_path / "zoning.png", lot, site)]
    assert all(Path(f).stat().st_size > 10_000 for f in figures)


def test_apartment_zoning_from_its_contract(tmp_path):
    out = draw_zoning(load_fixture("zoning_scheme", "apt_2br_interior"), tmp_path / "apt.png")
    assert out.stat().st_size > 10_000


def test_viz_rejects_a_wrong_contract(tmp_path):
    lot, site, _ = _contracts()
    with pytest.raises(ContractValidationError):
        draw_site(site, lot, tmp_path / "x.png")
