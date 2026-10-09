"""Command line.

spaceplan validate BRIEF
spaceplan capacity BRIEF [-o OUT] [--plot PNG] [--site-plot PNG] [--zoning-plot PNG] [--rules RULES] [--catalog CATALOG]
                   [--strategy auto|A_inscribed_rectangle|B_stepped_footprint|B_polygonal_footprint] [--no-corrections] [--json]
                   [--budget tight|medium|ample|FRACTION] [--cost-model base|weighted|shape]
spaceplan program TYPOLOGY [--garage N] [--profile P] [-o OUT]
spaceplan catalog [--markdown OUT]
spaceplan household ARCHETYPE|HOUSEHOLD.json [--tier T] [--no-next] [--dwelling house|apartment] [--culture P] [-o OUT] [--json]
spaceplan household --list
spaceplan household --rules-markdown OUT
spaceplan profiles BRIEF|ARCHETYPE [--culture P] [--budget L|F] [--cost-model M] [--zone] [--sheets DIR] [--lang es|en] [-o OUT]
spaceplan areas [LOT ...] [--households A.C,...] [--cost-model M] [--no-site] [--zone-top K] [--sheets DIR]
                [--tables DIR] [--scheme Vx] [--lang es|en] [--json] [--contract OUT]

Module commands (refactor tanda 4): each reads and writes module contracts (contracts/schemas).
spaceplan lotcap|site|zoning BRIEF [-o CONTRACT] [--strategy S] [--no-corrections] [--json]
spaceplan household BRIEF.json --contract OUT                 (program contract of a brief)
spaceplan cost --lot-capacity LC --site-plan SP --program PG [--brief BRIEF] [--budget L|F] [--cost-model M]
               [-o CONTRACT] [--json]
spaceplan profiles ... --contract OUT                          (program_portfolio contract)
spaceplan areas ... --contract OUT                             (area_matrix contract)
spaceplan viz [--lot-capacity LC] [--site-plan SP] [--zoning-scheme ZS] [--area-matrix AM] [--capacity-plot PNG]
              [--site-plot PNG] [--zoning-plot PNG] [--sheets DIR] [--lang es|en]
spaceplan capacity BRIEF ... --contracts DIR                   (writes every contract of the brief)
"""

from __future__ import annotations

import argparse
import json
import sys

from spaceplan.core.lib.catalog import CatalogError
from spaceplan.core.lib.contracts import ContractValidationError, load_contract, write_contract
from spaceplan.core.lib.schema_validation import BriefValidationError, validate_brief
from spaceplan.core.lib_aux.json_io import dump_json, load_json
from spaceplan.modules.household.lib.household import HouseholdError
from spaceplan.modules.household.lib.household_catalog import HouseholdCatalogError
from spaceplan.modules.household.main.run_household import load_catalogs, resolve_brief_program
from spaceplan.modules.household.main.run_program import build_program
from spaceplan.pipeline.main.run_capacity import run_capacity_contracts, run_capacity_file
from spaceplan.pipeline.main.run_catalog import parameter_table
from spaceplan.pipeline.main.run_household_report import derive_household


def _review_lines(review: dict) -> list[str]:
    s = review["summary"]
    lines = [
        f"program     net {s['net_area_sqft']:.0f} sq ft x {s['gross_factor']:g} = {s['gross_estimate_sqft']:.0f} gross"
        f"  (errors {review['counts']['error']}, warnings {review['counts']['warning']})"
    ]
    lines += [f"  {f['severity']:<8} {f['check_id']:<24} {f['subject']}: {f['message']}"
              for f in review["findings"] if f["severity"] != "info"]
    return lines


def _zoning_lines(package: dict) -> list[str]:
    lines = []
    for option in (package.get("zoning") or {}).get("options", []):
        if option["status"] in ("zoned", "no_valid_scheme"):
            lines.append(f"zoning {option['option_id']:<4} [{option['profile']}] {option['valid']} valid of "
                         f"{option['enumerated']} topologies ({option['variants_searched']} footprint x split variants)")
            for s in option["schemes"]:
                lines.append(f"           #{s['rank']} {s['scores']['total']:.2f}  {s['topology']['key']}  ({s['footprint_variant']})")
    return lines


def _backyard_lines(package: dict) -> list[str]:
    site = package.get("site_partition")
    if not site:
        return []
    lines = []
    for option in site["options"]:
        by = option.get("backyard")
        if not by:
            continue
        placed = [f"{e['element']} {e['area_sqft']:.0f}" for e in by["elements"] if e["status"] == "placed"]
        lines.append(f"backyard {option['option_id']:<3} yard {by['yard_area_sqft']:.0f} sq ft, green {by['green_fraction']:.0%} "
                     f"(min {by['min_green_fraction']:.0%}): {', '.join(placed) or 'nothing placed'}")
        lines += [f"           left out: {e['element']} - {e['reason']}" for e in by["elements"] if e["status"] == "excluded"]
    return lines


def _correction_lines(package: dict) -> list[str]:
    c = package.get("corrections")
    if not c:
        return []
    lines = [f"correction  {c['status']} ({c['triggered_by']}); {c['full_runs']} full run(s) of {c['candidates']}"]
    for r in c["evaluated"]:
        if r["outcome"] in (None, "not_evaluated"):
            continue
        lines.append(f"  cost {r['cost']:<5g} {r['strategy']:<22} garage {r['garage_layout']:<8} recess "
                     f"{r['front_recess_ft']:>4g} ft -> {r['outcome']}")
    for r in c["pareto"]:
        lines.append(f"  pareto{'*' if r['on_frontier'] else ' '} cost {r['cost']:<5g} score {r['score']:.3f} "
                     f"{', '.join(r['labels'])}")
    return lines


def _cost_lines(cost: dict | None) -> list[str]:
    if not cost:
        return []
    ref = cost["reference"]
    lines = [f"cost        model {cost['model']}, reading {cost['reading']} (1 = {ref['gross_area_sqft']:.0f} sq ft "
             f"{ref['label']}); {cost['legend']}"]
    for e in cost["options"]:
        models = "  ".join(f"{k} {v:.3f}" for k, v in e["by_model"].items())
        lines.append(f"  {e['label']:<14} {e['index']:.3f}   [{models}]  quantities {e['quantities']['confidence']}")
    b = cost["budget"]
    if b.get("applies"):
        budget = b["budget"]
        label = "none" if budget is None else f"{budget['level'] or 'fraction'} {budget['fraction_of_max']:g}"
        lines.append(f"  budget {label}: buildable max {b['buildable_max_index']:g}, governing {b['governing']}")
        lines += [f"  suggestion: {s}" for s in b["suggestions"]]
    t = cost.get("tornado")
    if t:
        target = t["a"] if t["b"] is None else f"{t['b']} - {t['a']}"
        lines.append(f"  tornado ({t['model']}, {target}, base {t['base']:+.4f}):")
        lines += [f"    {r['parameter']:<26} {r['at_low']:+.4f} .. {r['at_high']:+.4f}  swing {r['swing']:.4f}"
                  + ("  crosses zero" if r["crosses_zero"] else "") for r in t["rows"][:5]]
    return lines


def _profile_lines(result: dict) -> list[str]:
    c = result["ceilings"]
    lines = [f"profiles    {result['brief_id']}  reading {result['reading']}, model {result['model']}; "
             f"{result['legend']}",
             f"ceilings    FAR {c['far_sqft']} sq ft, one floor {c['one_floor_max_sqft']}, budget {c['budget_fraction']}; "
             f"maximum stopped by {c['governing']}"]
    for name in ("minimum", "optimum", "maximum", "accessible"):
        p = result["profiles"][name]
        cov = "-" if p["next_stage_coverage"] is None else f"{p['next_stage_coverage']:.0%}"
        zoning = p.get("zoning") or {}
        lines.append(f"  {name:<10} {p['gross_area_sqft']:6.0f} sq ft  index {p['index']:.3f}  quality {p['quality']:.2f}  "
                     f"next {cov:>4}  {p['feasibility']}" + (f"  zoning {zoning.get('status')}" if zoning else ""))
    s = result["profiles"]["staged"]
    lines.append(f"  staged     today {s['index_today']:.3f} + later {s['index_later']:.3f} = {s['index_total']:.3f} "
                 f"(final now {s['index_build_final_now']:.3f}, premium {s['staging_premium']:+.3f}); expansion "
                 f"{s['expansion_gross_sqft']:.0f} sq ft")
    lines.append("curve       " + " > ".join(p["move"] for p in result["curve"][1:]))
    lines += [f"sheet       {p}" for p in result["sheets"]]
    return lines


def _area_lines(result: dict) -> list[str]:
    lines = [f"areas       {len(result['lots'])} lots x {len(result['meta']['households'])} households, "
             f"model {result['meta']['model']}; {result['meta']['legend']}"]
    for lot in result["lots"]:
        b, s = lot["budget"], lot["summary"]
        io = "-" if b["io_max"] is None else f"{b['io_max']:.2f}"
        lines.append(f"  {b['lot_id']:<26} IC max {b['ic_max']:.2f} IO max {io:>4}  cells {s['cells']:4d}  "
                     f"best {dict(sorted(s['best_scheme_counts'].items()))}  status {s['status_counts']}")
        for e in lot["e2"]:
            lines.append(f"      E2 {e['household_id']} {e['profile']}: {e['status']} "
                         f"({e['valid']} zonings, {e['space_level_valid']} space layouts)")
    lines += [f"figure      {f}" for f in result.get("figures", [])]
    return lines


def _parse_households(value: str | None) -> list[tuple[str, str | None]] | None:
    if not value:
        return None
    out = []
    for item in value.split(","):
        arch, _, culture = item.strip().partition(".")
        out.append((arch, None if culture in ("", "none") else culture))
    return out


def _parse_budget(value: str | None) -> dict | None:
    if value is None:
        return None
    try:
        return {"fraction_of_max": float(value)}
    except ValueError:
        return {"level": value}


def _summary(package: dict) -> str:
    if not package["scope"]["in_scope"]:
        return "\n".join(["out of scope: " + "; ".join(package["scope"]["reasons"]), *_zoning_lines(package),
                          *_review_lines(package["program_review"]),
                          *[f"warning     {w}" for w in package["warnings"]]])
    cap = package["capacity"]
    rect = package["realizable_capacity"][0]
    lines = [
        f"brief       {package['meta']['brief_id']}  ({package['meta']['package_id']})",
        f"lot         {package['lot_metrics']['area_sqft']:.0f} sq ft",
        f"envelope    {cap['envelope']['area']['value']:.0f} sq ft [{cap['envelope']['area']['status']}]",
        f"FAR         {cap['far_ratio']['value']:.2f} -> {cap['gross_area_max']['value']:.1f} sq ft",
        f"strategy A  {rect['area']['value']:.0f} sq ft ({rect['utilization']['value']:.0%})",
        *[f"strategy {'B' + (str(r['steps']) if r.get('steps') else 'P'):<3} {r['area']['value']:.0f} sq ft "
          f"({r['utilization']['value']:.0%})" for r in package["realizable_capacity"][1:]],
        f"selected    {package['zoning'].get('selection', {}).get('strategy')} "
        f"({package['zoning'].get('selection', {}).get('reason')})" if package.get("zoning") else "selected    -",
        f"active      normative={cap['active_constraint_normative']['constraint']}  "
        f"effective={cap['active_constraint_effective']['constraint']}",
    ]
    for level in cap["feasibility"]["levels"]:
        lines.append(
            f"  {level['level']:<30} floors_min={level['floors_min']} cap={level['floors_cap']} "
            f"feasible={level['feasible']} [{level['status']}]"
        )
    site = package["site_partition"]
    for option in site["options"]:
        if "zones" not in option:
            lines.append(f"site {option['option_id']:<4} not feasible: {'; '.join(option['reasons'])}")
            continue
        paving = next(c for c in option["checks"] if c["check_id"] == "front_paving_fraction")
        mark = "*" if option["option_id"] == site["selected_option_id"] else " "
        lines.append(
            f"site {option['option_id']:<3}{mark} garden {option['zones']['garden']['area_sqft']:.0f} sq ft, "
            f"paving {paving['value']:.0%} ({option['access']['walkway_variant']}, deck {option['access']['deck_position']}), "
            f"feasible={option['feasible']} prefs={option['preferences_met']}"
        )
        lines += [f"           fix: {h}" for h in option.get("corrections", [])]
    lines += _zoning_lines(package) + _correction_lines(package) + _backyard_lines(package)
    lines += _cost_lines(package.get("cost"))
    lines += _review_lines(package["program_review"])
    lines += [f"warning     {w}" for w in package["warnings"]]
    return "\n".join(lines)


def _household_lines(result: dict, tier_filter: str | None) -> list[str]:
    comp = ", ".join(f"{k} {v}" for k, v in result["composition"].items() if v)
    lines = [(f"household   {result['archetype_id'] or 'custom'}  ({comp})  "
              f"[{result['household_catalog_id']} {result['household_catalog_version']}]")]

    def stage_lines(stage, label):
        out = [f"{label}"]
        for tier in ("required", "preferred", "desirable"):
            if tier_filter and tier != tier_filter:
                continue
            program, review = stage["programs"][tier], stage["reviews"][tier]
            rooms = [s["space_id"] for s in program["spaces"]]
            out.append(f"  {tier:<10} net {review['net_area_sqft']:5.0f}  gross {review['gross_estimate_sqft']:5.0f} sq ft  "
                       f"garage {program['garage_cars']}  driveway {stage['driveway_vehicles'][tier]}  "
                       f"errors {review['counts']['error']} warnings {review['counts']['warning']}")
            out.append("             " + ", ".join(rooms))
            out += [f"             {f['severity']}: {f['check_id']} {f['subject']}: {f['message']}" for f in review["findings"]]
        return out

    lines += stage_lines(result, "now")
    nxt = result.get("next_stage")
    if nxt:
        events = ", ".join(f"{e['event']}@{e['in_years']}y" for e in nxt["events_applied"]) or "aging only"
        lines += stage_lines(nxt, f"in {nxt['horizon_years']} years ({events})")
        delta = nxt["growth_delta"]
        lines.append(f"growth      gross {delta['gross_area_change_sqft']:+.0f} sq ft (preferred)")
        lines += [f"  {c['tier']:<10} {c['space_type']}:{c['household_role']} {c['now']} -> {c['next']}"
                  + (f" (ground {c['ground_now']} -> {c['ground_next']})" if c["ground_now"] != c["ground_next"] else "")
                  for c in delta["changes"]]
        lines += [f"  note: {n}" for n in delta["notes"]]
    culture = result.get("culture") or {}
    if culture.get("applied"):
        aspects = ", ".join(f"{k}={v}" for k, v in culture["aspects"].items())
        lines.append(f"culture     kitchen {culture['kitchen_typology']}; rules {', '.join(culture['rule_ids'])}")
        lines.append(f"  aspects   {aspects}")
        tier = tier_filter or "preferred"
        rel = ", ".join(f"{o['a']}-{o['b']} {o['type']}" + (f" {o['kind']}" if "kind" in o else "")
                        for o in culture["relation_overrides"][tier])
        lines.append(f"  relations ({tier}) {rel or '-'}")
        if culture["anchor_overrides"][tier]:
            lines.append("  anchors   " + ", ".join(f"{k} {v['mode']}" for k, v in culture["anchor_overrides"][tier].items()))
        yard = culture["backyard"][tier]
        if yard["elements"]:
            lines.append("  backyard  " + ", ".join(f"{k} #{v['priority']}" for k, v in yard["elements"].items())
                         + (f"; green >= {yard['min_green_fraction']['value']:.0%}" if yard["min_green_fraction"] else ""))
    else:
        lines.append("culture     none (no profile or aspects chosen)")
    lines += _cost_lines(result.get("cost"))
    lines.append(f"rules       {len(result['rule_trace'])} fired, {len(result['rules_not_fired'])} not fired")
    return lines


def _contract_lines(contract: dict) -> list[str]:
    name = contract["contract"]
    lines = [(f"contract    {name} {contract['version']} by {contract['produced_by']}  brief {contract.get('brief_id')}  "
              f"input {contract['input_sha256'][:12]}")]
    if name == "lot_capacity":
        cap = contract["capacity"]
        lines.append(f"  lot {contract['lot_metrics']['area_sqft']:.0f} sq ft, envelope {cap['envelope']['area']['value']:.0f}, "
                     f"FAR {cap['far_ratio']['value']:.2f} -> {cap['gross_area_max']['value']:.0f} sq ft, "
                     f"strategy {contract['realization_strategy']}")
    elif name == "site_plan":
        site = contract["site_partition"]
        lines += [f"  {o['option_id']}: {o['floors']} floor(s), feasible={o.get('feasible')}" for o in site["options"]]
    elif name == "zoning_scheme":
        lines += [f"  {o['option_id']}: {o['status']}" for o in (contract["zoning"] or {}).get("options", [])]
    elif name == "program":
        lines.append(f"  {len(contract['program']['spaces'])} spaces, buildable as stated: "
                     f"{contract['program_review']['buildable_as_stated']}")
    lines += [f"warning     {w}" for w in contract.get("warnings", [])]
    return lines


def _write_module_contract(contract: dict | None, out: str | None, as_json: bool, label: str) -> int:
    if contract is None:
        print(f"{label}: no contract for this brief (out of the capacity scope or no normative maximum)",
              file=sys.stderr)
        return 2
    if out:
        write_contract(contract, out)
    print(json.dumps(contract, indent=2) if as_json else "\n".join(_contract_lines(contract)))
    return 0


def _add_module_parsers(sub) -> None:
    for name, contract in (("lotcap", "lot_capacity"), ("site", "site_plan"), ("zoning", "zoning_scheme")):
        p = sub.add_parser(name, help=f"{name} module: run the capacity workflow and write the {contract} contract")
        p.add_argument("brief")
        p.add_argument("-o", "--out")
        p.add_argument("--strategy", default=None,
                       choices=("auto", "A_inscribed_rectangle", "B_stepped_footprint", "B_polygonal_footprint"))
        p.add_argument("--no-corrections", action="store_true")
        p.add_argument("--json", action="store_true")
    p_cost = sub.add_parser("cost", help="cost module: cost_report from the lot_capacity, site_plan and program contracts")
    p_cost.add_argument("--lot-capacity", required=True)
    p_cost.add_argument("--site-plan", required=True)
    p_cost.add_argument("--program", required=True)
    p_cost.add_argument("--brief", help="brief with a household block: adds the household tiers and its budget")
    p_cost.add_argument("--budget")
    p_cost.add_argument("--cost-model", choices=("base", "weighted", "shape"))
    p_cost.add_argument("-o", "--out")
    p_cost.add_argument("--json", action="store_true")
    p_viz = sub.add_parser("viz", help="viz module: figures from contracts")
    p_viz.add_argument("--lot-capacity")
    p_viz.add_argument("--site-plan")
    p_viz.add_argument("--zoning-scheme")
    p_viz.add_argument("--area-matrix")
    p_viz.add_argument("--capacity-plot")
    p_viz.add_argument("--site-plot")
    p_viz.add_argument("--zoning-plot")
    p_viz.add_argument("--sheets", help="directory for the area-matrix figures")
    p_viz.add_argument("--lang", choices=("es", "en"))


def _run_module_command(args) -> int:
    from spaceplan.pipeline.main.run_modules import (
        CONTRACT_OF_MODULE,
        capacity_contracts,
        cost_contract_for,
    )

    if args.command in ("lotcap", "site", "zoning"):
        contracts = capacity_contracts(load_json(args.brief), args.strategy, not args.no_corrections)
        return _write_module_contract(contracts.get(CONTRACT_OF_MODULE[args.command]), args.out, args.json,
                                      args.command)
    if args.command == "cost":
        report = cost_contract_for(load_contract(args.lot_capacity, "lot_capacity"),
                                   load_contract(args.site_plan, "site_plan"), load_contract(args.program, "program"),
                                   load_json(args.brief) if args.brief else None, args.cost_model,
                                   _parse_budget(args.budget))
        if report is not None and not args.json:
            if args.out:
                write_contract(report, args.out)
            print("\n".join(_contract_lines(report) + _cost_lines(report["cost"])))
            return 0
        return _write_module_contract(report, args.out, args.json, "cost")
    from spaceplan.modules.viz.main.run_viz import (
        draw_area_matrix,
        draw_capacity,
        draw_site,
        draw_zoning,
    )

    lc = load_contract(args.lot_capacity, "lot_capacity") if args.lot_capacity else None
    sp = load_contract(args.site_plan, "site_plan") if args.site_plan else None
    zs = load_contract(args.zoning_scheme, "zoning_scheme") if args.zoning_scheme else None
    figures = []
    if args.capacity_plot:
        figures.append(draw_capacity(_need(lc, "--lot-capacity"), args.capacity_plot))
    if args.site_plot:
        figures.append(draw_site(_need(lc, "--lot-capacity"), _need(sp, "--site-plan"), args.site_plot))
    if args.zoning_plot:
        zs = _need(zs, "--zoning-scheme")
        if zs["unit"] is None:
            _need(lc, "--lot-capacity")
        figures.append(draw_zoning(zs, args.zoning_plot, lc, sp))
    if args.area_matrix:
        figures += draw_area_matrix(load_contract(args.area_matrix, "area_matrix"), _need(args.sheets, "--sheets"),
                                    args.lang)
    if not figures:
        raise ValueError("viz: nothing to draw (give --capacity-plot, --site-plot, --zoning-plot or --area-matrix)")
    print("\n".join(f"figure      {f}" for f in figures))
    return 0


def _need(value, option: str):
    if value is None:
        raise ValueError(f"missing {option}")
    return value


def _is_brief(data: dict) -> bool:
    return isinstance(data, dict) and "dwelling_type" in data and "meta" in data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spaceplan")
    sub = parser.add_subparsers(dest="command", required=True)
    p_val = sub.add_parser("validate", help="validate a brief")
    p_val.add_argument("brief")
    p_cap = sub.add_parser("capacity", help="run the capacity layer and write the package")
    p_cap.add_argument("brief")
    p_cap.add_argument("-o", "--out")
    p_cap.add_argument("--rules")
    p_cap.add_argument("--plot")
    p_cap.add_argument("--catalog")
    p_cap.add_argument("--site-plot")
    p_cap.add_argument("--zoning-plot")
    p_cap.add_argument("--json", action="store_true", help="print the full package")
    p_cap.add_argument("--strategy", default=None,
                       choices=("auto", "A_inscribed_rectangle", "B_stepped_footprint", "B_polygonal_footprint"),
                       help="footprint realization (default: catalog realization.default)")
    p_cap.add_argument("--no-corrections", action="store_true",
                       help="skip the multivariable minimal correction when the one-floor option does not zone")
    p_cap.add_argument("--budget", help="relative budget: tight|medium|ample or a fraction of the lot maximum")
    p_cap.add_argument("--cost-model", choices=("base", "weighted", "shape"))
    p_cap.add_argument("--contracts", help="directory where every module contract of the brief is written")
    p_prog = sub.add_parser("program", help="expand a catalog typology into a brief program block")
    p_prog.add_argument("typology")
    p_prog.add_argument("--garage", type=int, choices=(0, 1, 2), default=2)
    p_prog.add_argument("--profile", default="balanced")
    p_prog.add_argument("-o", "--out")
    p_cat = sub.add_parser("catalog", help="print the parameter table with sources")
    p_cat.add_argument("--markdown")
    p_house = sub.add_parser("household", help="derive needs and programs from a household or an archetype")
    p_house.add_argument("household", nargs="?", help="archetype id or household JSON file")
    p_house.add_argument("--list", action="store_true", help="list the reference archetypes")
    p_house.add_argument("--tier", choices=("required", "preferred", "desirable"))
    p_house.add_argument("--no-next", action="store_true", help="skip the next stage")
    p_house.add_argument("--dwelling", choices=("house", "apartment"), default="house")
    p_house.add_argument("-o", "--out")
    p_house.add_argument("--json", action="store_true")
    p_house.add_argument("--cost-model", choices=("base", "weighted", "shape"))
    p_house.add_argument("--culture", choices=("latino", "anglo", "mixed", "custom"),
                         help="cultural profile preset chosen by the client (editable aspects in a JSON household)")
    p_house.add_argument("--rules-markdown", help="write the household rules and archetypes table and exit")
    p_house.add_argument("--contract", help="with a brief: write its program contract (household module)")
    p_prof = sub.add_parser("profiles", help="minimum / optimum / maximum, staged and accessible programs (step 6.5d)")
    p_prof.add_argument("source", help="brief with a household block (lot reading) or an archetype id (reference)")
    p_prof.add_argument("--culture", choices=("latino", "anglo", "mixed", "custom"))
    p_prof.add_argument("--budget", help="tight|medium|ample or a fraction of the lot maximum")
    p_prof.add_argument("--cost-model", choices=("base", "weighted", "shape"))
    p_prof.add_argument("--zone", action="store_true", help="zone every profile that fits one floor")
    p_prof.add_argument("--sheets", help="directory for the review and portfolio sheets")
    p_prof.add_argument("--lang", choices=("es", "en"))
    p_prof.add_argument("-o", "--out")
    p_prof.add_argument("--json", action="store_true")
    p_prof.add_argument("--contract", help="write the program_portfolio contract")
    p_area = sub.add_parser("areas", help="area matrix per lot: profile x vertical scheme x strategy (step 6.6)")
    p_area.add_argument("lots", nargs="*", help="pilot lot names or brief paths (default: the 10 pilot lots)")
    p_area.add_argument("--households", help="comma list archetype.culture (culture: none|latino|anglo)")
    p_area.add_argument("--cost-model", choices=("base", "weighted", "shape"))
    p_area.add_argument("--no-site", action="store_true", help="skip the measured site stage (E1)")
    p_area.add_argument("--zone-top", type=int, help="E2: zone the K best one-floor cells per lot")
    p_area.add_argument("--sheets", help="directory for the figures and E2 review sheets")
    p_area.add_argument("--tables", help="directory for area_matrix.json and the CSV tables")
    p_area.add_argument("--lang", choices=("es", "en"))
    p_area.add_argument("--scheme", action="append", default=[],
                        help="vertical scheme fixed by the client (V0-V5); evaluated even if not applicable")
    p_area.add_argument("--json", action="store_true")
    p_area.add_argument("--contract", help="write the area_matrix contract")
    _add_module_parsers(sub)
    args = parser.parse_args(argv)
    try:
        if args.command in ("lotcap", "site", "zoning", "cost", "viz"):
            return _run_module_command(args)
        if args.command == "validate":
            brief, _ = resolve_brief_program(load_json(args.brief))
            validate_brief(brief)
            print("brief is valid")
            return 0
        if args.command == "program":
            result = build_program(args.typology, args.garage, args.profile)
            if args.out:
                dump_json(result["program"], args.out)
            print(json.dumps(result["program"], indent=2))
            print("\n".join(_review_lines(result["review"])), file=sys.stderr)
            return 0
        if args.command == "household":
            _, hcat = load_catalogs()
            if args.rules_markdown:
                from spaceplan.pipeline.lib.catalog_table import render_household_table

                table = render_household_table(hcat)
                with open(args.rules_markdown, "w", encoding="utf-8") as fh:
                    fh.write(table)
                print(table)
                return 0
            if args.list or not args.household:
                for a in hcat.data["archetypes"]:
                    print(f"{a['archetype_id']:<18} {a['label']}: {a['description']}")
                return 0
            raw = load_json(args.household) if args.household.endswith(".json") else {"archetype_id": args.household}
            if args.contract:
                from spaceplan.pipeline.main.run_modules import program_contract_for

                if not _is_brief(raw):
                    raise ValueError("household --contract needs a brief (the program contract belongs to a brief)")
                return _write_module_contract(program_contract_for(raw), args.contract, args.json, "household")
            if args.culture:
                raw = {**raw, "cultural_profile": args.culture}
            result = derive_household(raw, dwelling_type=args.dwelling, next_stage=not args.no_next,
                                      cost_model=args.cost_model)
            if args.out:
                dump_json(result, args.out)
            print(json.dumps(result, indent=2) if args.json else "\n".join(_household_lines(result, args.tier)))
            return 0
        if args.command == "profiles":
            from spaceplan.pipeline.main.run_portfolio import run_profiles

            if args.source.endswith(".json"):
                source = load_json(args.source)
            else:
                source = {"household": {"archetype_id": args.source}, "meta": {"brief_id": args.source}}
            if args.culture:
                source.setdefault("household", {})["cultural_profile"] = args.culture
            if args.contract:
                from spaceplan.modules.profiles.main.contract import from_contract
                from spaceplan.pipeline.main.run_modules import portfolio_contract_for

                contract = portfolio_contract_for(source, _parse_budget(args.budget), args.cost_model, args.zone,
                                                  args.sheets, args.lang)
                write_contract(contract, args.contract)
                result = from_contract(contract)
            else:
                result = run_profiles(source, _parse_budget(args.budget), args.cost_model, args.zone, args.sheets,
                                      args.lang)
            if args.out:
                dump_json(result, args.out)
            print(json.dumps(result, indent=2) if args.json else "\n".join(_profile_lines(result)))
            return 0
        if args.command == "areas":
            from spaceplan.modules.areas.main.run_area_matrix import write_tables
            from spaceplan.pipeline.main.run_area_analysis import run_area_matrix

            result = run_area_matrix(args.lots or None, _parse_households(args.households), args.cost_model,
                                     not args.no_site, args.zone_top, args.sheets, args.lang,
                                     forced_schemes=tuple(args.scheme))
            if args.tables:
                write_tables(result, args.tables)
            if args.contract:
                from spaceplan.modules.areas.main.contract import to_contract

                write_contract(to_contract(result), args.contract)
            print(json.dumps(result, indent=2, default=str) if args.json else "\n".join(_area_lines(result)))
            return 0
        if args.command == "catalog":
            table = parameter_table()
            if args.markdown:
                with open(args.markdown, "w", encoding="utf-8") as fh:
                    fh.write(table)
            print(table)
            return 0
        if args.contracts:
            package, contracts = run_capacity_contracts(load_json(args.brief), args.rules, args.plot, args.catalog,
                                                        args.site_plot, args.zoning_plot, args.strategy,
                                                        not args.no_corrections, cost_model=args.cost_model,
                                                        budget=_parse_budget(args.budget))
            from pathlib import Path

            Path(args.contracts).mkdir(parents=True, exist_ok=True)
            for name, contract in contracts.items():
                write_contract(contract, Path(args.contracts) / f"{name}.json")
            if args.out:
                dump_json(package, args.out)
        else:
            package = run_capacity_file(args.brief, args.out, args.rules, args.plot, args.catalog, args.site_plot,
                                        args.zoning_plot, args.strategy, not args.no_corrections,
                                        cost_model=args.cost_model, budget=_parse_budget(args.budget))
        print(json.dumps(package, indent=2) if args.json else _summary(package))
        return 0
    except (HouseholdError, HouseholdCatalogError) as exc:
        print(exc, file=sys.stderr)
        return 2
    except CatalogError as exc:
        print(exc, file=sys.stderr)
        return 2
    except ValueError as exc:  # unknown budget level or cost model
        print(exc, file=sys.stderr)
        return 2
    except BriefValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    except ContractValidationError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
