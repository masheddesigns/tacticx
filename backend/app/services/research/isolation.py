"""Phase 29 production isolation fingerprinting.

Captures hashes of production model files + configuration before research
runs; verification proves research left production untouched. Read-only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

BACKEND_ROOT = Path(__file__).parent.parent.parent.parent

# Production files locked for Phase 29 (model math + production config).
LOCKED_FILES = [
    "app/services/predictions/ensemble.py",
    "app/services/predictions/elo.py",
    "app/services/predictions/poisson.py",
    "app/services/predictions/outputs.py",
    "app/services/predictions/montecarlo.py",
    "app/services/predictions/advanced.py",
]


def file_hashes(files: List[str]) -> Dict[str, str]:
    out = {}
    for rel in files:
        path = BACKEND_ROOT / rel
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def production_fingerprint() -> Dict[str, Any]:
    """Capture the locked production state (files + config)."""
    from app.services.acquisition.readiness_gate import (
        DEFAULT_MODEL_ID,
        READINESS_CONFIG_REGISTRY,
        get_prediction_config,
    )
    from dataclasses import asdict

    config = get_prediction_config(DEFAULT_MODEL_ID)
    return {
        "model_files": file_hashes(LOCKED_FILES),
        "default_model_id": DEFAULT_MODEL_ID,
        "readiness_config": asdict(config),
        "registry_models": sorted(READINESS_CONFIG_REGISTRY.keys()),
    }


def verify_fingerprint(before: Dict[str, Any]) -> Dict[str, Any]:
    """Compare current production state against a captured fingerprint."""
    after = production_fingerprint()
    file_drift = [rel for rel in LOCKED_FILES
                  if before.get("model_files", {}).get(rel)
                  != after["model_files"].get(rel)]
    config_drift = before.get("readiness_config") != after.get("readiness_config")
    registry_drift = before.get("registry_models") != after.get("registry_models")
    intact = not file_drift and not config_drift and not registry_drift
    return {
        "intact": intact,
        "file_drift": file_drift,
        "config_drift": config_drift,
        "registry_drift": registry_drift,
    }
