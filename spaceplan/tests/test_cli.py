import json

from spaceplan.lib_aux.json_io import load_resource_json
from spaceplan.main.cli import main


def test_cli_capacity_writes_package_and_plot(tmp_path, capsys):
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps(load_resource_json("spaceplan", "data", "briefs", "fan_curve_35_80x100.json")))
    out, png = tmp_path / "pkg.json", tmp_path / "plot.png"
    assert main(["capacity", str(brief), "-o", str(out), "--plot", str(png)]) == 0
    assert json.loads(out.read_text())["capacity"]["feasibility"]["false_infeasible_risk"] is True
    assert png.stat().st_size > 10_000
    assert "false-infeasible risk" in capsys.readouterr().out


def test_cli_validate_reports_errors(tmp_path, capsys):
    data = load_resource_json("spaceplan", "data", "briefs", "interior_50x100.json")
    data["streets"][0]["role"] = "secondary"
    brief = tmp_path / "bad.json"
    brief.write_text(json.dumps(data))
    assert main(["validate", str(brief)]) == 2
    assert "primary street" in capsys.readouterr().err


def test_cli_program_and_catalog(tmp_path, capsys):
    out = tmp_path / "program.json"
    assert main(["program", "t3_standard", "--garage", "1", "--profile", "social", "-o", str(out)]) == 0
    program = json.loads(out.read_text())
    assert any(s["space_type"] == "garage_1car" for s in program["spaces"])
    md = tmp_path / "table.md"
    assert main(["catalog", "--markdown", str(md)]) == 0
    assert "## Space types" in md.read_text()
    assert main(["program", "t9_castle"]) == 2
