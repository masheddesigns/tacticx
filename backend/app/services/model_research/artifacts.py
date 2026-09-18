"""Research artifacts: hashed JSON payloads + registry linkage (Phase 12).

Running the same experiment twice yields identical predictions, metrics,
feature ordering and artifact hashes where computation is deterministic
(numpy-only, fixed order, seeded bootstrap). Mutable results are never
cached without version keys: artifact filenames embed dataset + model +
seed, and re-runs overwrite only byte-identical content (verified, not
assumed — mismatch raises).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "data" / "research"


def artifact_key(dataset_version: str, model_version: str, seed: int,
                 extra: str = "") -> str:
    base = f"{dataset_version}__{model_version}__seed{seed}"
    if extra:
        base += f"__{extra}"
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in base)
    return safe


def payload_hash(payload: Dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     default=str).encode()).hexdigest()


def save_artifact(key: str, name: str, payload: Dict) -> str:
    directory = ARTIFACT_ROOT / key
    directory.mkdir(parents=True, exist_ok=True)
    digest = payload_hash(payload)
    envelope = {"artifact_hash": digest, "payload": payload}
    path = directory / f"{name}.json"
    if path.exists():
        previous = json.loads(path.read_text())
        if previous.get("artifact_hash") != digest:
            raise ValueError(
                f"artifact {key}/{name} differs from stored version: "
                "deterministic re-runs must be byte-identical")
        return str(path)
    path.write_text(json.dumps(envelope, indent=2, default=str))
    return str(path)


def load_artifact(key: str, name: str) -> Dict:
    path = ARTIFACT_ROOT / key / f"{name}.json"
    return json.loads(path.read_text())
