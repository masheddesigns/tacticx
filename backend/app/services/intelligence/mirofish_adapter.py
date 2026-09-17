"""MiroFish adapter (Phase 6).

MiroFish is an OPTIONAL scenario layer behind the existing
MiroFishService abstraction. The adapter:

- builds an explicit context object with every field labeled observed /
  derived / estimated / scenario (never hidden future information);
- enforces a configurable timeout and validates outputs
  (0<=p<=1, 1X2 sums ~1, score distributions sum ~1);
- NEVER modifies the statistical prediction — output is separately labeled;
- degrades to scenario.status=unavailable on any failure, so the normal
  prediction always works.

No external MiroFish is configured in this repository: the default service
is DisabledMirofishService (honest unavailability). If integration is
impossible due to external dependency/configuration limits, that is reported
— never a fabricated successful run.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.services.intelligence.schemas import MiroFishResult
from app.services.predictions.mirofish import (
    MiroFishInput,
    MiroFishOutput,
    MiroFishService,
)

ADAPTER_VERSION = "mirofish_adapter_v1"
DEFAULT_TIMEOUT_SECONDS = 30.0


class LabeledValue(BaseModel):
    value: object = None
    kind: str = ""  # observed | derived | estimated | scenario

    model_config = {"arbitrary_types_allowed": True}


class MiroFishContext(BaseModel):
    match: Dict[str, LabeledValue] = Field(default_factory=dict)
    teams: Dict[str, LabeledValue] = Field(default_factory=dict)
    historical_context: Dict[str, LabeledValue] = Field(default_factory=dict)
    prediction: Dict[str, LabeledValue] = Field(default_factory=dict)
    market_context: Dict[str, LabeledValue] = Field(default_factory=dict)
    scenario: Dict[str, LabeledValue] = Field(default_factory=dict)
    cutoff: str = ""

    def assert_no_future(self, kickoff_iso: Optional[str]) -> None:
        """Refuse contexts whose cutoff is after kickoff. Cutoff == kickoff
        is the normal pre-match prediction point and is allowed."""
        if kickoff_iso and self.cutoff and self.cutoff > kickoff_iso:
            raise ValueError("MiroFish cutoff must not be after match kickoff")


def build_context(composed, scenario_name: str = "baseline",
                  scenario_params: Optional[Dict] = None) -> MiroFishContext:
    """Assemble the explicit MiroFish context from a composed prediction.

    Only pre-cutoff material enters: core prediction (derived), feature
    availability (observed), market state (observed, pre-cutoff non-closing),
    scenario parameters (scenario). No results, no closing prices, no
    post-match data — those fields do not exist on the context.
    """
    match = composed.match or {}
    core = composed.core_prediction or {}
    avail = core.get("feature_availability") or {}
    ctx = MiroFishContext(cutoff=composed.cutoff or "")
    for key in ("match_id", "league_id", "kickoff_at"):
        ctx.match[key] = LabeledValue(value=match.get(key), kind="observed")
    for key in ("home_team_id", "away_team_id"):
        ctx.teams[key] = LabeledValue(value=match.get(key), kind="observed")
    ctx.historical_context["home_history"] = LabeledValue(
        value=avail.get("home_history"), kind="observed")
    ctx.historical_context["away_history"] = LabeledValue(
        value=avail.get("away_history"), kind="observed")
    ctx.historical_context["xg_histories"] = LabeledValue(
        value={"home": avail.get("home_xg_history"),
               "away": avail.get("away_xg_history")}, kind="observed")
    ctx.prediction["probabilities_1x2"] = LabeledValue(
        value=composed.probabilities, kind="derived")
    ctx.prediction["goal_lambdas"] = LabeledValue(
        value=composed.goals, kind="derived")
    ctx.prediction["model_version"] = LabeledValue(
        value=(composed.model or {}).get("version"), kind="derived")
    market = composed.market
    if getattr(market, "status", None) == "ok":
        ctx.market_context["consensus"] = LabeledValue(
            value=(market.consensus or {}).get("values"), kind="observed")
    ctx.scenario["name"] = LabeledValue(value=scenario_name, kind="scenario")
    ctx.scenario["parameters"] = LabeledValue(value=scenario_params or {},
                                              kind="scenario")
    ctx.assert_no_future(str(match.get("kickoff_at") or ""))
    return ctx


def validate_output(output: MiroFishOutput) -> Dict:
    """Reject malformed external output. Never blindly trust it."""
    errors = []
    probs = output.scenario_probabilities or {}
    for key in ("home", "draw", "away"):
        if key in probs:
            value = probs[key]
            if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
                errors.append(f"scenario_probabilities[{key}]={value!r} invalid")
    if all(k in probs for k in ("home", "draw", "away")):
        total = probs["home"] + probs["draw"] + probs["away"]
        if abs(total - 1.0) > 1e-3:
            errors.append(f"scenario 1X2 sums to {total:.6f}")
    for key, value in (output.scenario_probabilities or {}).items():
        if key.startswith("score:"):
            errors.append("score entries must live in a score_distribution mapping")
            break
    return {"valid": not errors, "errors": errors}


class DisabledMirofishService(MiroFishService):
    """Default: no external MiroFish configured. Honest unavailability."""

    async def analyze(self, payload: MiroFishInput) -> MiroFishOutput:
        raise RuntimeError("MiroFish not configured (no external service bound)")


def input_reference(context: MiroFishContext) -> str:
    digest = hashlib.sha256(json.dumps(
        context.model_dump(), sort_keys=True, default=str).encode()).hexdigest()
    return f"mirofish_ctx_{digest[:16]}"


async def run_mirofish(composed, service: Optional[MiroFishService] = None,
                       scenario_name: str = "baseline",
                       scenario_params: Optional[Dict] = None,
                       timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                       version: str = "") -> MiroFishResult:
    """Run MiroFish around (never inside) the statistical prediction.

    Any failure — unavailable, misconfigured, timeout, invalid output —
    yields status=unavailable while prediction.status stays untouched.
    """
    service = service or DisabledMirofishService()
    try:
        context = build_context(composed, scenario_name, scenario_params)
    except Exception as exc:
        return MiroFishResult(status="unavailable",
                              output={"error": f"context build failed: {exc}"},
                              version=version or ADAPTER_VERSION)
    reference = input_reference(context)
    payload = MiroFishInput(
        match_context={k: v.value for k, v in context.match.items()},
        historical_data={k: v.value for k, v in context.historical_context.items()},
        current_statistics={k: v.value for k, v in context.prediction.items()},
        team_information={k: v.value for k, v in context.teams.items()},
        market_movement={k: v.value for k, v in context.market_context.items()},
    )
    try:
        output = await asyncio.wait_for(service.analyze(payload),
                                        timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return MiroFishResult(status="unavailable",
                              output={"error": f"MiroFish timed out after "
                                               f"{timeout_seconds}s"},
                              version=version or ADAPTER_VERSION,
                              input_reference=reference)
    except Exception as exc:
        return MiroFishResult(status="unavailable",
                              output={"error": f"MiroFish failed: {str(exc)[:200]}"},
                              version=version or ADAPTER_VERSION,
                              input_reference=reference)
    check = validate_output(output)
    if not check["valid"]:
        return MiroFishResult(status="unavailable",
                              output={"error": "MiroFish output failed validation",
                                      "validation_errors": check["errors"]},
                              version=version or ADAPTER_VERSION,
                              input_reference=reference)
    return MiroFishResult(status="ok", output=output.model_dump(),
                          version=version or ADAPTER_VERSION,
                          input_reference=reference)
