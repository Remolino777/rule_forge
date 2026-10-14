"""Workflow of the space-quality indicators (step 6.7a S2.2a): stack_plan contracts + design profile -> report.

    run_quality(paths, profile=None, out_dir=None)   report dict; with out_dir also quality_summary.json,
                                                      quality_by_type.csv, quality_spaces.csv, quality_doors.csv
                                                      (S2.2e), quality.md
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from spaceplan.core.lib_aux.json_io import dump_json, load_json
from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.space_quality import quality_report

OVERALL_LABELS = {
    "cells_spaced": "casas con planta completa",
    "pct_over_pref": "% de espacios sobre la proporción preferida",
    "pct_over_max": "% de espacios sobre la proporción máxima",
    "pct_under_min_side": "% bajo el lado mínimo del catálogo",
    "pct_furniture_misfit": "% donde no cabe el mobiliario de referencia",
    "fragmented_spaces": "espacios partidos en piezas",
    "irregular_circulation": "pasillos y foyers no rectangulares",
    "circulation_fraction_median": "fracción de circulación (mediana por planta)",
    "hall_long_ft_median": "tramo de pasillo más largo (mediana, ft)",
    "pct_n_not_daylit": "% de espacios N más hondos que la profundidad de luz",
    "closets_by_role": "clósets por rol (recámara, blancos, baño)",
    "m_spaces_with_facade": "espacios M que ocupan fachada",
    "m_facade_ft": "fachada ocupada por espacios M (ft)",
    "pct_over_cap": "% de espacios sobre su área máxima efectiva (S2.2e)",
    "suite": "suite principal: dormitorio y suite completa (mediana y máximo) y su relación con el garage",
    "doors": "interferencias de puertas (R1 giros, E1 excepción en suite, R1b hoja, R2 fuera del ambiente, R3 paso)",
    "floors_with_door_conflicts": "plantas con alguna interferencia de puertas",
    "floors": "plantas medidas",
    "extra_room": "ambiente adicional: casas donde cabe / agregado",
    "structure": "estructura de la planta alta (muros sobre muros de abajo, luces, vigas, postes) (S2.2f)",
    "arrival": "llegada de la escalera arriba (halls, lado corto de la llegada, puertas de dormitorios) (S2.2f)",
    "rooms": ("dormitorios (S2.2j): paso dentro del cuarto, cama con holguras, baño por el walk-in, principal mayor, "
              "aparatos del baño, tiras, hojas sobre muro, puertas angostas, huéspedes y respaldos del programa"),
}


def _markdown(report: dict[str, Any], profile_id: str) -> str:
    o = report["overall"]
    lines = [f"# Calidad de espacios (perfil {profile_id})", "", "| Indicador | Valor |", "|---|---|"]
    lines += [f"| {label} | {o.get(k)} |" for k, label in OVERALL_LABELS.items()]
    lines += ["", ("| tipo | n | prop. mediana | p90 | > pref % | > máx % | < lado mín % | mueble no cabe % | "
                   "no rect. % | partido % | corto × largo (mediana) | área mediana | área p90 | área máx | "
                   "> tope % |"), "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["by_type"]:
        lines.append(f"| {r['space_type']} | {r['n']} | {r['aspect_median']} | {r['aspect_p90']} | {r['pct_over_pref']} | "
                     f"{r['pct_over_max']} | {r['pct_under_min_side']} | {r['pct_furniture_misfit']} | "
                     f"{r['pct_not_rectangular']} | {r['pct_fragmented']} | {r['short_median_ft']} × "
                     f"{r['long_median_ft']} | {r['area_median']} | {r['area_p90']} | {r['area_max']} | "
                     f"{r['pct_over_cap']} |")
    return "\n".join(lines) + "\n"


def run_quality(paths: list[str], profile: dict[str, Any] | None = None, out_dir: str | None = None) -> dict:
    reg = load_registry()
    values = dp.effective_values(reg, profile)
    report = quality_report([load_json(p) for p in paths], values)
    report["profile_id"] = (profile or {}).get("profile_id", "baseline")
    report["registry_version"] = reg.version
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        dump_json({k: v for k, v in report.items() if k != "cells"}, out / "quality_summary.json")
        with open(out / "quality_by_type.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(report["by_type"][0]) if report["by_type"] else ["space_type"])
            w.writeheader()
            w.writerows(report["by_type"])
        rows = [{"cell_id": c["cell_id"], "profile": c["profile"], **s} for c in report["cells"] for s in c["spaces"]]
        with open(out / "quality_spaces.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["cell_id"])
            w.writeheader()
            w.writerows(rows)
        doors = [{"cell_id": c["cell_id"], "floor": key, **f, "doors": " ".join(map(str, f["doors"])),
                  "spaces": " ".join(f["spaces"])}
                 for c in report["cells"] for key, fl in c["floors"].items() for f in fl["door_findings"]]
        with open(out / "quality_doors.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["cell_id", "floor", "rule", "doors", "spaces", "area_sqft", "exception"])
            w.writeheader()
            w.writerows(doors)
        (out / "quality.md").write_text(_markdown(report, report["profile_id"]), encoding="utf-8")
    return report


def quality_lines(report: dict[str, Any]) -> list[str]:
    o = report["overall"]
    return [f"{label}: {o.get(k)}" for k, label in OVERALL_LABELS.items()]


__all__ = ["OVERALL_LABELS", "quality_lines", "run_quality"]
