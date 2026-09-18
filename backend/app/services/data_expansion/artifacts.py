"""Coverage-delta artifacts (Phase 13).

Before/after snapshots with delta table, stored as JSON. Old dataset
versions stay accessible: artifacts are additive files, never overwrites
(exists + different content raises — same policy as research artifacts).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "data" / "expansion"


def payload_hash(payload: Dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     default=str).encode()).hexdigest()


def save_delta(name: str, payload: Dict) -> str:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    digest = payload_hash(payload)
    envelope = {"artifact_hash": digest, "payload": payload}
    path = ARTIFACT_ROOT / f"{name}.json"
    if path.exists():
        previous = json.loads(path.read_text())
        if previous.get("artifact_hash") != digest:
            raise ValueError(f"delta artifact {name} differs from stored version")
        return str(path)
    path.write_text(json.dumps(envelope, indent=2, default=str))
    return str(path)
