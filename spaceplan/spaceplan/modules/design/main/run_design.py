"""Workflow of the design module (step 6.7a S2.2a): the `spaceplan design` commands.

    list        parameters (filters: prefix, who, kind, text)
    explain     one parameter: value, range or choices, code limit, source
    propose     validate a change against the profile (nothing written)
    apply       write a new profile with the changes (validated as a whole)
    diff        effective differences between two profiles (or a profile and the baseline)
    check       validate the registry baseline and, optionally, a profile
    tools       write the LLM tool definitions (data/schemas/design_tools.json by default)
    materialize write the stores (catalogs and rulesets) with a profile applied, for a pipeline run
    criteria    area budget or door interference criteria by layer, with the effective maximum per space for a
                house size (S2.2e); change them with `apply --set <id>=<value>` or the LLM tool set_criteria
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spaceplan.core.lib.contracts import write_contract
from spaceplan.core.lib_aux.json_io import dump_json, load_json, load_resource_json
from spaceplan.modules.design.lib import area_criteria as ac
from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import (
    RULESET_PREFIX,
    DesignRegistry,
    load_registry,
)
from spaceplan.modules.design.lib.llm_tools import tool_definitions
from spaceplan.modules.design.main.contract import from_contract, to_contract

BASELINE_PROFILE = ("data", "design", "profiles", "baseline.json")


def parse_value(text: str) -> Any:
    """JSON when it parses (numbers, true/false, lists), otherwise the text itself."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def load_profile(path: str | None) -> dict[str, Any]:
    if path is None:
        return from_contract(load_resource_json("spaceplan", *BASELINE_PROFILE))
    data = load_json(path)
    return from_contract(data) if data.get("contract") == "design_profile" else data


def _fmt(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict, bool)) else str(v)


def list_lines(reg: DesignRegistry, profile: dict, prefix=None, who=None, kind=None, text=None,
               lang: str = "es") -> list[str]:
    snap = {r["id"]: r for r in dp.snapshot(reg, profile, lang)}
    rows = reg.list(prefix, who, kind, text)
    lines = [f"{len(rows)} parameters (registry {reg.registry_id} {reg.version}, profile {profile['profile_id']})"]
    for p in rows:
        r = snap[p.id]
        mark = "*" if r["changed"] else " "
        lines.append(f"{mark} {p.id:48s} {_fmt(r['value']):>14s} {p.unit or '':6s} {r['kind']:9s} {p.who:8s} "
                     f"{r['description']}")
    return lines


def explain_lines(reg: DesignRegistry, profile: dict, param_id: str, lang: str = "es") -> list[str]:
    row = next(r for r in dp.snapshot(reg, profile, lang) if r["id"] == param_id) if param_id in reg.params \
        else reg.explain(param_id, lang)
    lines = [f"{row['id']}: {row['description']}",
             (f"  value {_fmt(row['value'])} {row['unit'] or ''} (baseline {_fmt(row['baseline'])}); "
              f"kind {row['kind']} (allowed {row['kinds_allowed']}); defined by {row['who']}")]
    if row["range"]:
        lines.append(f"  range {row['range']}")
    if row["choices"] is not None:
        lines.append(f"  choices {row['choices']}")
    if row["floor"]:
        f = row["floor"]
        lines.append(f"  code limit ({f['bound']}) {f['value']:g} {f['unit'] or ''}: {f['rule_id']} - {f['source']}")
    lines.append(f"  source: {row['source'].get('document', '')} {row['source'].get('section', '')}".rstrip())
    lines.append(f"  verified: {row['verified']}; store {row['store']} -> {row['path']}")
    if row.get("note"):
        lines.append(f"  note: {row['note']}")
    return lines


def criteria_lines(view: dict[str, Any]) -> list[str]:
    """Plain-text table of a criteria view (area or doors)."""
    if view["group"] in (ac.DOORS, ac.STRUCTURE):
        return [f"{view['group']} criteria"] + [f"  {r['id']:42s} {_fmt(r['value']):>8s} {r['unit'] or '':6s} "
                                                 f"{r['kind']:9s} {r['description']}" for r in view["rules"]]
    lines = [f"area criteria{' for a house of ' + format(view['house_net_sqft'], '.0f') + ' sq ft net (size factor ' + format(view['size_factor'], '.3f') + ')' if view.get('house_net_sqft') else ''}"]
    lines.append("  policy:")
    lines += [f"    {r['id']:42s} {_fmt(r['value']):>20s} {r['unit'] or '':6s} {r['description']}" for r in view["policy"]]
    lines.append(f"  whole suite cap: {view['suite_total_cap_sqft']} sq ft; extra package: "
                 f"{view['extra_package']['types']} {view['extra_package']['net_sqft']} sq ft")
    lines.append(f"  {'space':16s} {'code':>6s} {'p.min':>6s} {'p.tgt':>6s} {'p.max':>6s} {'rec':>6s} {'cap':>6s} "
                 f"{'share':>6s} {'eff.cap':>8s} binding")
    for s in view["spaces"]:
        prog, des = s["layers"]["program"], s["layers"]["design"]

        def val(d, k):
            return _fmt(d[k]["value"]) if k in d else "-"
        code = s["layers"].get("code")
        eff = s.get("effective") or {}
        lines.append(f"  {s['space_type']:16s} {format(code['value'], 'g') if code else '-':>6s} "
                     f"{val(prog, 'program_min_sqft'):>6s} {val(prog, 'program_target_sqft'):>6s} "
                     f"{val(prog, 'program_max_sqft'):>6s} {val(des, 'rec_sqft'):>6s} {val(des, 'cap_sqft'):>6s} "
                     f"{val(des, 'share_max'):>6s} {_fmt(eff.get('cap_sqft', '-')):>8s} {eff.get('binding', '')}")
    return lines


def write_profile(profile: dict, out: str) -> None:
    write_contract(to_contract(profile), out)


def materialize_to(reg: DesignRegistry, profile: dict, out_dir: str) -> list[str]:
    """Write the stores with the profile applied: catalog.json (merged), stacking_catalog.json, rules/<file>."""
    stores = dp.materialize(reg, profile)
    out = Path(out_dir)
    (out / "rules").mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in stores.items():
        path = out / "rules" / name[len(RULESET_PREFIX):] if name.startswith(RULESET_PREFIX) else out / f"{name}.json"
        dump_json(data, path)
        written.append(str(path))
    return written


def run_design_command(args) -> int:
    reg = load_registry()
    profile = load_profile(getattr(args, "profile", None))
    lang = getattr(args, "lang", None) or "es"
    action = args.design_action
    if action == "list":
        rows = list_lines(reg, profile, args.prefix, args.who, args.kind, args.text, lang)
        print(json.dumps([r for r in dp.snapshot(reg, profile, lang) if r["id"] in
                          {p.id for p in reg.list(args.prefix, args.who, args.kind, args.text)}], indent=2,
                         ensure_ascii=False) if args.json else "\n".join(rows))
        return 0
    if action == "explain":
        print("\n".join(explain_lines(reg, profile, args.id, lang)))
        return 0
    if action == "propose":
        result = dp.propose(reg, profile, args.id, parse_value(args.value) if args.value is not None else dp.UNSET,
                            args.kind, lang)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{'OK' if result['ok'] else 'REJECTED'} {result['id']}: {_fmt(result['current'])} -> "
                  f"{_fmt(result['proposed'])} {result['unit'] or ''} (kind {result['kind']})")
            for x in result["problems"]:
                print(f"  problem: {x}")
            for x in result["warnings"]:
                print(f"  warning: {x}")
        return 0 if result["ok"] else 2
    if action == "apply":
        changes = []
        for item in args.set or []:
            pid, _, raw = item.partition("=")
            changes.append({"id": pid, "value": parse_value(raw)})
        for item in args.kind_of or []:
            pid, _, kind = item.partition("=")
            changes.append({"id": pid, "kind": kind})
        if args.new:
            profile = dp.new_profile(reg, args.new)
        try:
            new = dp.apply(reg, profile, changes, args.author, args.date or datetime.now(UTC).date().isoformat(), args.reason)
        except dp.ProfileError as exc:
            for x in exc.problems:
                print(f"problem: {x}")
            return 2
        write_profile(new, args.out)
        print(f"profile {new['profile_id']}: {len(new['changes'])} changes -> {args.out}")
        return 0
    if action == "diff":
        a = load_profile(args.a) if args.a else None
        b = load_profile(args.b)
        rows = dp.diff(reg, a, b)
        print(json.dumps(rows, indent=2, ensure_ascii=False) if args.json else "\n".join(
            [f"{len(rows)} differences"] + [(f"  {r['id']}: {_fmt(r['a'])} -> {_fmt(r['b'])} {r['unit'] or ''}"
                                              + (f" (kind {r['kind_a']} -> {r['kind_b']})"
                                                 if r['kind_a'] != r['kind_b'] else "")) for r in rows]))
        return 0
    if action == "check":
        problems = reg.self_check()
        warnings: list[str] = []
        if getattr(args, "profile", None):
            p2, warnings = dp.check_profile(reg, profile)
            problems += p2
        for x in problems:
            print(f"problem: {x}")
        for x in warnings:
            print(f"warning: {x}")
        print(f"{len(reg.params)} parameters, {len(reg.constraints)} constraints: "
              f"{'OK' if not problems else f'{len(problems)} problems'}")
        return 0 if not problems else 2
    if action == "tools":
        out = args.out or str(Path(__file__).resolve().parents[3] / "data" / "schemas" / "design_tools.json")
        dump_json(tool_definitions(reg), out)
        print(f"{len(tool_definitions(reg)['tools'])} tools over {len(reg.params)} parameters -> {out}")
        return 0
    if action == "criteria":
        values, kinds = dp.effective_values(reg, profile), reg.kinds(dp.change_map(profile))
        view = ac.criteria_view(reg, values, kinds, args.group, args.space_type, args.house_net, lang)
        print(json.dumps(view, indent=2, ensure_ascii=False) if args.json else "\n".join(criteria_lines(view)))
        return 0
    if action == "materialize":
        written = materialize_to(reg, profile, args.out)
        print(f"{len(written)} stores written to {args.out}")
        return 0
    raise ValueError(f"unknown design action {action!r}")


def add_design_parser(sub) -> None:
    p = sub.add_parser("design", help="design module (step 6.7a S2.2a): registry of the design parameters, profiles "
                                      "and LLM tool definitions")
    acts = p.add_subparsers(dest="design_action", required=True)

    def common(q, profile=True):
        if profile:
            q.add_argument("--profile", help="design profile (contract or plain JSON); default: the baseline")
        q.add_argument("--lang", choices=("es", "en"))
        q.add_argument("--json", action="store_true")

    q = acts.add_parser("list")
    q.add_argument("--prefix")
    q.add_argument("--who", choices=("client", "designer", "code"))
    q.add_argument("--kind", choices=("hard", "soft", "weight", "reference"))
    q.add_argument("--text")
    common(q)
    q = acts.add_parser("explain")
    q.add_argument("id")
    common(q)
    q = acts.add_parser("propose")
    q.add_argument("id")
    q.add_argument("value", nargs="?")
    q.add_argument("--kind", choices=("hard", "soft", "weight", "reference"))
    common(q)
    q = acts.add_parser("apply")
    q.add_argument("--new", help="start a new profile with this id instead of --profile")
    q.add_argument("--set", action="append", help="ID=VALUE (repeat); VALUE as JSON or text")
    q.add_argument("--kind-of", action="append", help="ID=KIND (repeat)")
    q.add_argument("--author", required=True)
    q.add_argument("--date", help="YYYY-MM-DD (default today)")
    q.add_argument("--reason", default="")
    q.add_argument("-o", "--out", required=True)
    common(q)
    q = acts.add_parser("diff")
    q.add_argument("b", help="profile")
    q.add_argument("--a", help="first profile (default: the baseline)")
    common(q, profile=False)
    q = acts.add_parser("check")
    common(q)
    q = acts.add_parser("tools")
    q.add_argument("-o", "--out")
    common(q, profile=False)
    q = acts.add_parser("criteria")
    q.add_argument("--group", choices=ac.GROUPS, default=ac.AREA)
    q.add_argument("--space-type")
    q.add_argument("--house-net", type=float, help="net program area of the house (sq ft, garage excluded)")
    common(q)
    q = acts.add_parser("materialize")
    q.add_argument("-o", "--out", required=True)
    common(q)


__all__ = ["BASELINE_PROFILE", "add_design_parser", "criteria_lines", "explain_lines", "list_lines", "load_profile",
           "materialize_to", "parse_value", "run_design_command", "write_profile"]
