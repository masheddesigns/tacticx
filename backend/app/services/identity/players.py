"""Deterministic player identity resolution (Phase 1.7).

Priority (mirrors team identity):
  1. known (source, provider_player_id) mapping
  2. legacy Player row (provider, provider_player_id)
  3. deterministic normalized identity: name (+ team when known),
     exactly one candidate
  4. explicit alias dictionary (reuse team-alias config shape via
     PLAYER_ALIASES_JSON; defaults to team aliases for shared nicknames)
  5. otherwise UNRESOLVED — never guess, no fuzzy matching.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Player
from app.db.models.provenance import PlayerProviderMapping
from app.logging_config import get_logger
from app.services.identity.normalize import normalize_name

log = get_logger(__name__)

METHOD_MAPPING = "mapping"
METHOD_LEGACY = "legacy_provider_id"
METHOD_NORMALIZED = "normalized_identity"
METHOD_ALIAS = "alias"
METHOD_CREATED = "created"


class PlayerIdentityResolver:
    def __init__(self, db: Session, aliases: Optional[dict] = None):
        self.db = db
        self.aliases = aliases if aliases is not None else get_settings().player_aliases

    def _canonical_form(self, name: str) -> str:
        expanded = self.aliases.get(name) or self.aliases.get(normalize_name(name)) or name
        return normalize_name(expanded)

    def resolve(
        self,
        source: str,
        provider_player_id: str = "",
        provider_player_name: str = "",
        team_id: Optional[int] = None,
    ) -> tuple[Optional[int], str]:
        """Return (player_id | None, method). None means UNRESOLVED."""
        db, src = self.db, (source or "").lower()

        # 1. Known mapping for this source's native ID.
        if provider_player_id:
            mapping = (
                db.query(PlayerProviderMapping)
                .filter_by(source=src, provider_player_id=str(provider_player_id), active=True)
                .first()
            )
            if mapping and db.get(Player, mapping.player_id):
                return mapping.player_id, METHOD_MAPPING

        # 2. Legacy provider columns on the Player row itself.
        if provider_player_id:
            player = (
                db.query(Player)
                .filter_by(provider=src, provider_player_id=str(provider_player_id))
                .first()
            )
            if player:
                self._store_mapping(player.id, None, src, str(provider_player_id),
                                    provider_player_name, METHOD_LEGACY)
                return player.id, METHOD_LEGACY

        norm = normalize_name(provider_player_name)
        if not norm:
            return None, "unresolved"

        # 3. Deterministic normalized identity — exactly one candidate.
        # Alias-aware on both sides (order-independent), team-scoped first.
        query = db.query(Player).all()
        want = self._canonical_form(provider_player_name)
        method = METHOD_ALIAS if want != norm else METHOD_NORMALIZED
        candidates = [p for p in query if self._canonical_form(p.name) == want]
        if team_id is not None:
            scoped = [p for p in candidates if p.team_id == team_id]
            if len(scoped) == 1:
                self._store_mapping(scoped[0].id, team_id, src, str(provider_player_id or ""),
                                    provider_player_name, method)
                return scoped[0].id, method
            if len(scoped) > 1:
                log.warning("player identity ambiguous name=%r team=%s", provider_player_name, team_id)
                return None, "unresolved"
            # No same-team candidate: fall through to global handling below.
        if len(candidates) == 1:
            self._store_mapping(candidates[0].id, team_id, src, str(provider_player_id or ""),
                                provider_player_name, method)
            return candidates[0].id, method
        if len(candidates) > 1:
            log.warning("player identity ambiguous name=%r candidates=%s",
                        provider_player_name, [p.id for p in candidates])
            return None, "unresolved"

        # 4. Explicit alias dictionary, then normalized match.
        alias_target = self.aliases.get(provider_player_name) or self.aliases.get(norm)
        if alias_target:
            alias_norm = normalize_name(alias_target)
            aliased = [p for p in db.query(Player).all()
                       if self._canonical_form(p.name) == alias_norm]
            if team_id is not None:
                aliased = [p for p in aliased if p.team_id == team_id] or aliased
            if len(aliased) == 1:
                self._store_mapping(aliased[0].id, team_id, src, str(provider_player_id or ""),
                                    provider_player_name, METHOD_ALIAS)
                return aliased[0].id, METHOD_ALIAS
            return None, "unresolved"

        return None, "unresolved"

    def ensure(
        self,
        source: str,
        provider_player_id: str = "",
        provider_player_name: str = "",
        team_id: Optional[int] = None,
        position: Optional[str] = None,
    ) -> tuple[int, str]:
        """Resolve, creating a canonical player + mapping when genuinely new."""
        player_id, method = self.resolve(source, provider_player_id, provider_player_name,
                                         team_id=team_id)
        if player_id is not None:
            return player_id, method
        name = (provider_player_name or "").strip()
        if not name:
            raise ValueError("cannot create player without a name")
        src = (source or "").lower()
        legacy_pid = str(provider_player_id or "") or f"name:{normalize_name(name)}"
        clashing = (
            self.db.query(Player)
            .filter_by(provider=src, provider_player_id=legacy_pid)
            .first()
        )
        if clashing:
            if normalize_name(clashing.name) == normalize_name(name):
                self._store_mapping(clashing.id, team_id, src, legacy_pid, name,
                                    METHOD_NORMALIZED)
                return clashing.id, METHOD_NORMALIZED
            raise ValueError(
                f"player identity collision in {src}: {name!r} vs {clashing.name!r}")
        player = Player(name=name, team_id=team_id, position=position,
                        provider=src, provider_player_id=legacy_pid)
        self.db.add(player)
        self.db.flush()
        self._store_mapping(player.id, team_id, src, legacy_pid, name, METHOD_CREATED)
        self.db.commit()
        return player.id, METHOD_CREATED

    def _store_mapping(self, player_id: int, team_id: Optional[int], source: str,
                       provider_player_id: str, provider_player_name: str,
                       method: str) -> None:
        key = provider_player_id or f"name:{normalize_name(provider_player_name)}"
        existing = (
            self.db.query(PlayerProviderMapping)
            .filter_by(source=source, provider_player_id=key)
            .first()
        )
        if existing:
            return
        self.db.add(PlayerProviderMapping(
            player_id=player_id, team_id=team_id, source=source, provider_player_id=key,
            provider_player_name=provider_player_name or "",
            normalized_name=normalize_name(provider_player_name),
            resolution_method=method, active=True,
        ))
        self.db.commit()
