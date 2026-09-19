"""Scenario definitions sourced from the Phase 15 engine (Phase 16).

Only whitelisted deterministic scenario IDs may be sent to MiroFish. Each
definition carries the exact parameters, the baseline hash it was derived
from, and its own hash — the provider must echo all three.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.services.intelligence import scenarios as scenario_engine
from app.services.mirofish.contracts import ScenarioDefinition, payload_hash


def allowed_scenario_ids() -> List[str]:
    return sorted(scenario_engine.SCENARIOS)


def build_definition(baseline_1x2: Dict[str, float], lambda_home: float,
                     lambda_away: float, scenario_id: str,
                     baseline_hash: str) -> ScenarioDefinition:
    """Materialize one whitelisted scenario. Unknown IDs raise (whitelist)."""
    if scenario_id not in scenario_engine.SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario_id} "
                         f"(known: {sorted(scenario_engine.SCENARIOS)})")
    output = scenario_engine.run_scenario(baseline_1x2, lambda_home,
                                          lambda_away, scenario_id)
    dumped = output.model_dump()
    scenario_hash = payload_hash({
        "scenario_id": scenario_id,
        "parameters": dumped.get("parameters", {}),
        "probabilities": dumped.get("probabilities", {}),
        "goals": dumped.get("goals", {}),
    })
    return ScenarioDefinition(
        scenario_id=scenario_id,
        parameters={k: v for k, v in dumped.get("parameters", {}).items()
                    if k in ("kind", "home_mult", "away_mult", "description")},
        baseline_hash=baseline_hash,
        scenario_hash=scenario_hash,
    )


def definition_payload(definition: ScenarioDefinition) -> Dict[str, Any]:
    return definition.model_dump()
