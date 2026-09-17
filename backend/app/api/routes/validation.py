"""Phase 5 validation artifact endpoints.

Serves deterministic run artifacts produced by scripts/phase5_validate.py
and scripts/phase5_deepdive.py. Read-only: no evaluation is triggered here,
no parameters are tuned, and no betting content exists anywhere.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.evaluation.artifacts import ARTIFACT_ROOT, load_artifact
from app.services.evaluation.regimes import MODEL_STATUS_REGISTRY, default_policy

router = APIRouter(tags=["validation"])


def _safe_name(value: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in value)


@router.get("/validation/phase5/runs")
def list_runs() -> dict:
    """Run ids with available artifact names (newest first)."""
    if not ARTIFACT_ROOT.exists():
        return {"runs": []}
    runs = []
    for directory in sorted(ARTIFACT_ROOT.iterdir(), reverse=True):
        if directory.is_dir():
            runs.append({"run_id": directory.name,
                         "artifacts": sorted(p.stem for p in directory.glob("*.json"))})
    return {"runs": runs}


@router.get("/validation/phase5/runs/{run_id}/{artifact}")
def get_artifact(run_id: str, artifact: str) -> dict:
    """One stored artifact payload (e.g. baseline_report, deepdive_report)."""
    safe_run, safe_art = _safe_name(run_id), _safe_name(artifact)
    path = ARTIFACT_ROOT / safe_run / f"{safe_art}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return load_artifact(safe_run, safe_art)


@router.get("/validation/phase5/model-registry")
def model_registry() -> dict:
    """Model status registry + default selection policy (informational)."""
    return {"models": MODEL_STATUS_REGISTRY, "policy": default_policy()}


@router.get("/validation/phase5/disclaimer")
def disclaimer() -> dict:
    return {"disclaimer":
            "Probabilities are statistical estimates with honest uncertainty, "
            "never certainties. Past performance does not predict future results. "
            "No betting, staking, or guaranteed-outcome content is provided."}
