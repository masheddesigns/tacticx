"""Deterministic team identity resolution (Phase 1.6).

Priority:
  1. known (source, provider_team_id) mapping
  2. legacy Team row (provider, provider_team_id)
  3. deterministic normalized-name match, alias-aware on BOTH sides
     (order-independent) — exactly one candidate
  4. explicit alias dictionary (manually curated, config-driven)
  5. otherwise UNRESOLVED — never guess, no fuzzy matching.

Successful resolutions via 3/4 persist a mapping row for auditability.
`resolve()` is pure (never creates teams); `ensure()` creates a canonical
team + mapping for genuinely new names (used by bulk importers).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Team
from app.db.models.provenance import TeamProviderMapping
from app.logging_config import get_logger
from app.services.identity.normalize import normalize_name

log = get_logger(__name__)

METHOD_MAPPING = "mapping"
METHOD_LEGACY = "legacy_provider_id"
METHOD_NORMALIZED = "normalized_name"
METHOD_ALIAS = "alias"
METHOD_CREATED = "created"


class TeamIdentityResolver:
    def __init__(self, db: Session, aliases: Optional[dict] = None):
        self.db = db
        self.aliases = aliases if aliases is not None else get_settings().team_aliases

    def _canonical_form(self, name: str) -> str:
        """Single-hop alias expansion + normalization.

        Comparing BOTH sides through the alias map makes resolution
        order-independent: whichever variant was stored first, the other
        variant still resolves to it. Strictly deterministic — the map is
        explicit config, single hop, no chains, no fuzzy matching.
        """
        expanded = self.aliases.get(name) or self.aliases.get(normalize_name(name)) or name
        return normalize_name(expanded)

    def resolve(
        self,
        source: str,
        provider_team_id: str = "",
        provider_team_name: str = "",
        league: str = "",
        country: Optional[str] = None,
    ) -> tuple[Optional[int], str]:
        """Return (team_id | None, method). None means UNRESOLVED."""
        db, src = self.db, (source or "").lower()

        # 1. Known mapping for this source's native ID.
        if provider_team_id:
            mapping = (
                db.query(TeamProviderMapping)
                .filter_by(source=src, provider_team_id=str(provider_team_id), active=True)
                .first()
            )
            if mapping and db.get(Team, mapping.team_id):
                return mapping.team_id, METHOD_MAPPING

        # 2. Legacy provider columns on the Team row itself.
        if provider_team_id:
            team = (
                db.query(Team)
                .filter_by(provider=src, provider_team_id=str(provider_team_id))
                .first()
            )
            if team:
                self._store_mapping(team.id, src, str(provider_team_id),
                                    provider_team_name, league, country, METHOD_LEGACY)
                return team.id, METHOD_LEGACY

        norm = normalize_name(provider_team_name)
        if not norm:
            return None, "unresolved"

        # 3. Deterministic normalized-name match — exactly one candidate.
        # Both sides pass through the alias map first (order-independent).
        want = self._canonical_form(provider_team_name)
        via_alias = want != norm
        candidates = [
            t for t in db.query(Team).all() if self._canonical_form(t.name) == want
        ]
        method = METHOD_ALIAS if via_alias else METHOD_NORMALIZED
        if len(candidates) == 1:
            team_id = candidates[0].id
            self._store_mapping(team_id, src, str(provider_team_id or ""),
                                provider_team_name, league, country, method)
            return team_id, method
        if len(candidates) > 1:
            log.warning("team identity ambiguous name=%r candidates=%s",
                        provider_team_name, [t.id for t in candidates])
            return None, "unresolved"

        # 4. Explicit alias dictionary (variant -> canonical), then normalized match.
        alias_target = self.aliases.get(provider_team_name) or self.aliases.get(norm)
        if alias_target:
            alias_norm = normalize_name(alias_target)
            aliased = [t for t in db.query(Team).all() if normalize_name(t.name) == alias_norm]
            if len(aliased) == 1:
                team_id = aliased[0].id
                self._store_mapping(team_id, src, str(provider_team_id or ""),
                                    provider_team_name, league, country, METHOD_ALIAS)
                return team_id, METHOD_ALIAS
            return None, "unresolved"

        return None, "unresolved"

    def ensure(
        self,
        source: str,
        provider_team_id: str = "",
        provider_team_name: str = "",
        league_id: Optional[int] = None,
        league: str = "",
        country: Optional[str] = None,
    ) -> tuple[int, str]:
        """Resolve, creating a canonical team + mapping when genuinely new."""
        team_id, method = self.resolve(source, provider_team_id, provider_team_name,
                                       league=league, country=country)
        if team_id is not None:
            return team_id, method
        name = (provider_team_name or "").strip()
        if not name:
            raise ValueError("cannot create team without a name")
        src = (source or "").lower()
        # Sources without native IDs (CSVs) share provider_team_id="" — which
        # would collide on the legacy unique key. Namespace by normalized name.
        legacy_pid = str(provider_team_id or "") or f"name:{normalize_name(name)}"
        clashing = (
            self.db.query(Team)
            .filter_by(provider=src, provider_team_id=legacy_pid)
            .first()
        )
        if clashing:
            if normalize_name(clashing.name) == normalize_name(name):
                self._store_mapping(clashing.id, src, legacy_pid, name, league, country,
                                    METHOD_NORMALIZED)
                return clashing.id, METHOD_NORMALIZED
            raise ValueError(
                f"team identity collision in {src}: {name!r} vs {clashing.name!r}")
        team = Team(name=name, league_id=league_id,
                    country=country, provider=src, provider_team_id=legacy_pid)
        self.db.add(team)
        self.db.flush()
        self._store_mapping(team.id, src, legacy_pid, name, league, country, METHOD_CREATED)
        self.db.commit()
        return team.id, METHOD_CREATED

    def _store_mapping(self, team_id: int, source: str, provider_team_id: str,
                       provider_team_name: str, league: str, country: Optional[str],
                       method: str) -> None:
        existing = (
            self.db.query(TeamProviderMapping)
            .filter_by(source=source, provider_team_id=provider_team_id or f"name:{normalize_name(provider_team_name)}")
            .first()
        )
        if existing:
            return
        key = provider_team_id or f"name:{normalize_name(provider_team_name)}"
        self.db.add(TeamProviderMapping(
            team_id=team_id, source=source, provider_team_id=key,
            provider_team_name=provider_team_name or "", normalized_name=normalize_name(provider_team_name),
            country=country, league=league or "", resolution_method=method, active=True,
        ))
        self.db.commit()
