from conftest import load_brief
from spaceplan.main.run_capacity import run_capacity


def test_coastal_overlay_is_out_of_scope():
    brief = load_brief("interior_50x100")
    brief["overlays"]["coastal"] = True
    pkg = run_capacity(brief)
    assert pkg["scope"]["in_scope"] is False
    assert pkg["capacity"] is None
    assert any("coastal" in r for r in pkg["scope"]["reasons"])


def test_other_zone_is_out_of_scope():
    brief = load_brief("interior_50x100")
    brief["meta"]["zone"] = "RS-1-6"
    assert run_capacity(brief)["scope"]["in_scope"] is False
