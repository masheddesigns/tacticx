"""Phase 5 run artifacts: deterministic filenames, JSON payloads, metadata."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "data" / "phase5"


def run_id(model_name: str, dataset_fingerprint: str, scope: str) -> str:
    """Deterministic run id: phase5_{model}_{scope}_{datasetfp8}."""
    fp = (dataset_fingerprint or "unknown")[:8]
    safe_scope = "".join(c if (c.isalnum() or c in "-_") else "_" for c in scope)
    safe_model = "".join(c if (c.isalnum() or c in "-_") else "_" for c in model_name)
    return f"phase5_{safe_model}_{safe_scope}_{fp}"


def dataset_fingerprint(db_url: str = "sqlite:////tmp/p17.db") -> str:
    """Fingerprint the evaluation dataset: match count + max updated_at + leagues."""
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM matches")).scalar()
        max_updated = conn.execute(text("SELECT MAX(updated_at) FROM matches")).scalar()
        rows = conn.execute(
            text("SELECT l.code, m.kickoff_at FROM matches m "
                 "LEFT JOIN leagues l ON l.id = m.league_id")).fetchall()
    from collections import Counter

    def season_label(kickoff) -> str:
        try:
            from datetime import datetime as _dt

            value = _dt.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            return str(value.year if value.month >= 8 else value.year - 1)
        except Exception:
            return "unknown"

    leagues = sorted(Counter((str(code), season_label(ko)) for code, ko in rows).items())
    payload = {"count": count, "max_updated": str(max_updated),
               "leagues": [[code, season, n] for (code, season), n in leagues]}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest


def environment_metadata(extra: Optional[Dict] = None) -> Dict:
    """Python version, platform, git SHA (best-effort), UTC timestamp."""
    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                 text=True, timeout=10).stdout.strip() or None
    except Exception:
        git_sha = None
    meta = {"python": platform.python_version(),
            "platform": platform.platform(),
            "git_sha": git_sha,
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    if extra:
        meta.update(extra)
    return meta


def save_artifact(run_id_str: str, name: str, payload: Dict) -> str:
    """Write data/phase5/<run_id>/<name>.json; return the path."""
    directory = ARTIFACT_ROOT / run_id_str
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)


def load_artifact(run_id_str: str, name: str) -> Dict:
    path = ARTIFACT_ROOT / run_id_str / f"{name}.json"
    return json.loads(path.read_text())
