"""Feature quality dimensions (Phase 9).

identity_quality, temporal_quality, source_quality, sample_size_quality,
definition_quality are preserved as components with a high/medium/low/
unknown label. Components are never collapsed into one number without
preservation; availability (available true/false) stays separate from
quality (available=false + quality=unknown is valid).
"""
from __future__ import annotations

from typing import Dict


def assess(identity: str = "unknown", temporal: str = "unknown",
           source: str = "unknown", sample_size: str = "unknown",
           definition: str = "unknown") -> Dict:
    components = {"identity_quality": identity, "temporal_quality": temporal,
                  "source_quality": source, "sample_size_quality": sample_size,
                  "definition_quality": definition}
    # Temporal uses verified/estimated/unknown vocabulary; map to the
    # high/medium/low/unknown label scale without losing the raw dimension.
    scale = {"verified": "high", "estimated": "medium"}
    order = {"unknown": -1, "low": 0, "medium": 1, "high": 2}
    labeled = {k: (scale.get(v, v) if k == "temporal_quality" else v)
               for k, v in components.items()}
    worst = min(labeled.values(), key=lambda v: order.get(v, -1))
    if all(v == "unknown" for v in labeled.values()):
        label = "unknown"
    else:
        label = worst if worst != "unknown" else "low"
    return {"components": components, "quality": label}


def for_mode(mode_value: str, n_matches: int, identity_ok: bool = True) -> Dict:
    if n_matches == 0:
        temporal = "unknown"
    elif mode_value == "strict_prematch":
        temporal = "verified"
    else:
        temporal = "estimated"
    sample = "high" if n_matches >= 5 else ("medium" if n_matches >= 3 else (
        "low" if n_matches > 0 else "unknown"))
    return assess(identity="high" if identity_ok else "low",
                  temporal=temporal if n_matches else "unknown",
                  source="high", sample_size=sample, definition="high")
