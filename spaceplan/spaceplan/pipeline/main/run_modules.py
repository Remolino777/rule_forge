"""Module entry points that read and write contracts (refactor tanda 4), used by the per-module CLI commands.

    capacity_contracts(brief)      lot_capacity, site_plan, zoning_scheme, program and cost_report of a brief (the
                                   capacity workflow; site and zoning need lotcap's in-memory geometry, so their
                                   commands run the upstream modules first)
    program_contract_for(brief)    program contract only (household resolution + program review, no lot)
    cost_contract_for(...)         cost_report from the lot_capacity, site_plan and program contracts (no lot,
                                   site or zoning computation)
    portfolio_contract_for(...)    program_portfolio of a brief or an archetype
    area_matrix_contract_for(...)  area_matrix of the pilot (or a subset)
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.core.lib.schema_validation import validate_brief
from spaceplan.modules.areas.main.contract import to_contract as area_matrix_contract
from spaceplan.modules.cost.main.contract import cost_from_contracts
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.household.main.contract import to_contract as program_contract
from spaceplan.modules.household.main.run_household import resolve_brief_household
from spaceplan.modules.lotcap.main.run_lotcap import flag_lot_body
from spaceplan.modules.profiles.main.contract import to_contract as portfolio_contract
from spaceplan.pipeline.main.run_area_analysis import run_area_matrix
from spaceplan.pipeline.main.run_capacity import run_capacity_contracts
from spaceplan.pipeline.main.run_portfolio import run_profiles

MODULE_OF_CONTRACT = {"lot_capacity": "lotcap", "site_plan": "site", "zoning_scheme": "zoning", "program": "household",
                      "cost_report": "cost", "program_portfolio": "profiles", "area_matrix": "areas"}
CONTRACT_OF_MODULE = {m: c for c, m in MODULE_OF_CONTRACT.items()}


def capacity_contracts(brief: dict, strategy: str | None = None, corrections: bool = True,
                       cost_model: str | None = None, budget: dict | None = None,
                       catalog_path: str | Path | None = None) -> dict[str, dict]:
    """Contracts of the capacity workflow for a brief (houses in scope: all five; apartments: program and
    zoning_scheme; houses out of scope: program)."""
    return run_capacity_contracts(brief, catalog_path=catalog_path, strategy=strategy, corrections=corrections,
                                  cost_model=cost_model, budget=budget)[1]


def program_contract_for(brief: dict, catalog_path: str | Path | None = None) -> dict:
    """Same program contract the capacity workflow produces, without planning the lot."""
    resolved, household_block, _ = resolve_brief_household(brief, catalog_path)
    validate_brief(resolved)
    body, _ = flag_lot_body(resolved)
    review = review_program(load_catalog(catalog_path), load_ruleset_resource(*CRC_RULESET), body["program"])
    return program_contract(body, review, household_block)


def cost_contract_for(lot_capacity: dict, site_plan: dict, program: dict, brief: dict | None = None,
                      cost_model: str | None = None, budget: dict | None = None,
                      catalog_path: str | Path | None = None) -> dict | None:
    """cost_report from contracts; the brief (optional) adds the household tiers and its budget."""
    tiers = None
    if brief is not None:
        _, _, tiers = resolve_brief_household(brief, catalog_path)
        budget = budget if budget is not None else brief.get("budget")
    return cost_from_contracts(load_catalog(catalog_path), lot_capacity, site_plan, program, tiers, cost_model, budget)


def portfolio_contract_for(source: dict, budget: dict | None = None, cost_model: str | None = None,
                           zone: bool = False, sheets_dir=None, lang: str | None = None) -> dict:
    portfolio = run_profiles(source, budget, cost_model, zone, sheets_dir, lang)
    return portfolio_contract(portfolio, {"source": source, "budget": budget, "cost_model": cost_model,
                                          "zone": zone})


def area_matrix_contract_for(**kwargs) -> dict:
    return area_matrix_contract(run_area_matrix(**kwargs))


__all__ = ["CONTRACT_OF_MODULE", "MODULE_OF_CONTRACT", "area_matrix_contract_for", "capacity_contracts",
           "cost_contract_for", "portfolio_contract_for", "program_contract_for"]
