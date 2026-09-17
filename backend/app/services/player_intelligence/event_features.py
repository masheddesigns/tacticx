"""Event-feature registry (Phase 9).

Every event-derived metric carries: canonical name, source, source
field/event type, aggregation, semantic definition, temporal requirements,
quality requirements. Only what the source schema reliably represents is
registered — shots, passes, tackles, carries, pressures and assists are NOT
registered because match_events contains no reliable equivalent (audited
2026-09-17: types are goal/penalty/own_goal/missed_penalty/substitution/
yellow_card/second_yellow/red_card). No generic performance score exists.
"""
from __future__ import annotations

from typing import Dict, List, Optional

EVENT_FEATURE_DEFINITIONS: Dict[str, Dict] = {
    "goals": {
        "source": "statsbomb",
        "source_event_types": ["goal"],
        "aggregation": "count per appearance; rates per appearance (minutes unavailable)",
        "definition": "Goals credited to the player (penalties included as recorded; "
                      "own goals excluded — they credit the opponent).",
        "temporal_requirements": "event parent match finished before cutoff; "
                                 "strict requires explicit effective_at",
        "quality_requirements": "player identity resolved; minute present or not "
                                "(counts do not need minutes)",
    },
    "penalties_scored": {
        "source": "statsbomb",
        "source_event_types": ["penalty"],
        "aggregation": "count per appearance",
        "definition": "Penalty goals as recorded by the source event type.",
        "temporal_requirements": "as goals",
        "quality_requirements": "as goals",
    },
    "own_goals": {
        "source": "statsbomb",
        "source_event_types": ["own_goal"],
        "aggregation": "count per appearance (attributed against the player's team)",
        "definition": "Own goals put through the player's own net.",
        "temporal_requirements": "as goals",
        "quality_requirements": "as goals",
    },
    "yellow_cards": {
        "source": "statsbomb",
        "source_event_types": ["yellow_card", "second_yellow"],
        "aggregation": "count per appearance",
        "definition": "Cautions shown (second yellows counted once, as recorded).",
        "temporal_requirements": "as goals",
        "quality_requirements": "as goals",
    },
    "red_cards": {
        "source": "statsbomb",
        "source_event_types": ["red_card"],
        "aggregation": "count per appearance",
        "definition": "Straight red cards as recorded.",
        "temporal_requirements": "as goals",
        "quality_requirements": "as goals",
    },
    "substitute_appearances": {
        "source": "statsbomb",
        "source_event_types": ["substitution"],
        "aggregation": "count of substitution events involving the player "
                       "(lineup is_starting=0 is the appearance source of truth)",
        "definition": "Substitution on/off events; appearance attribution comes "
                      "from lineup rows, events are corroboration only.",
        "temporal_requirements": "as goals",
        "quality_requirements": "as goals",
    },
}

# Deliberately NOT registered (no reliable source equivalent):
UNREGISTERED = ("shots", "shots_on_target", "assists", "key_passes", "passes",
                "pass_completion", "progressive_passes", "tackles", "interceptions",
                "blocks", "clearances", "pressures", "recoveries", "carries",
                "dribbles", "minutes_played")


def definition(name: str) -> Optional[Dict]:
    return EVENT_FEATURE_DEFINITIONS.get(name)


def registered_names() -> List[str]:
    return sorted(EVENT_FEATURE_DEFINITIONS)


def is_supported(name: str) -> bool:
    return name in EVENT_FEATURE_DEFINITIONS
