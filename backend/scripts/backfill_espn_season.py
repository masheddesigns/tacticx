"""Backfill full 2026 seasons for MLS / ISL / Liga Argentina / Brasileirao from ESPN core API.

Real provider data only. Idempotent via provider_match_id = espn_{slug}_{event_id}.
Run inside the scheduler container (has app env + deps):
    docker cp backfill_espn_americas_isl.py tacticx-local-scheduler:/tmp/ && \
    docker exec tacticx-local-scheduler python /tmp/backfill_espn_americas_isl.py
"""
import json
import time
import urllib.request
from datetime import datetime

from sqlalchemy import text

from app.db.models.core import League, Match, Team
from app.db.session import get_session_local
from app.services.match_progression import _teams_match

BASE = "https://sports.core.api.espn.com/v2/sports/soccer"

LEAGUES = {
    # app_code: (espn_slug, season_year, display_name, country)
    "MLS": ("usa.1", 2026, "Major League Soccer", "USA"),
    "ISL": ("ind.1", 2026, "Indian Super League", "India"),
    "LIGA_ARG": ("arg.1", 2026, "Liga Profesional Argentina", "Argentina"),
    "BRA_SERIE_A": ("bra.1", 2026, "Brasileirao Serie A", "Brazil"),
}

_cache: dict = {}


def get(url):
    if url in _cache:
        return _cache[url]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            _cache[url] = data
            return data
        except Exception as e:  # noqa: BLE001 - transient network
            last = e
            time.sleep(2)
    raise last


def map_status(name: str):
    n = (name or "").upper()
    if "FULL_TIME" in n or "FINAL" in n or "FULLTIME" in n:
        return "FINISHED", 90
    if "HALFTIME" in n or "HALF_TIME" in n:
        return "HALFTIME", 45
    if "PROGRESS" in n or "FIRST_HALF" in n or "SECOND_HALF" in n or "OVERTIME" in n:
        return "LIVE", None
    if "POSTPONED" in n or "CANCELED" in n or "CANCELLED" in n or "ABANDONED" in n or "SUSPENDED" in n:
        return "POSTPONED", None
    return "SCHEDULED", None


def resolve_score(cdata):
    sc = cdata.get("score")
    if isinstance(sc, dict) and "$ref" in sc:
        try:
            sc = get(sc["$ref"]).get("value", sc.get("displayValue"))
        except Exception:  # noqa: BLE001
            return None
    try:
        return int(sc) if sc is not None else None
    except (ValueError, TypeError):
        return None


def resolve_team(db, league_id, espn_team_id, display, abbr):
    key = ("team", espn_team_id)
    if key in _cache:
        tid = _cache[key]
        return db.get(Team, tid)
    existing = db.query(Team).filter_by(provider="espn", provider_team_id=f"espn-{espn_team_id}").first()
    if existing:
        _cache[key] = existing.id
        return existing
    for t in db.query(Team).filter(Team.league_id == league_id).all():
        if _teams_match(t.name, display) or (abbr and _teams_match(t.name, abbr)):
            # bind ESPN id to the existing row for future runs
            t.provider = t.provider or "espn"
            db.flush()
            _cache[key] = t.id
            return t
    t = Team(league_id=league_id, name=display, short_name=(abbr or display)[:32],
             country="", provider="espn", provider_team_id=f"espn-{espn_team_id}")
    db.add(t)
    db.flush()
    _cache[key] = t.id
    return t


def main():
    import sys
    only = set(a.upper() for a in sys.argv[1:]) or None
    db = get_session_local()()
    added = skipped = 0
    try:
        from sqlalchemy import text
        # Hand-seeded explicit IDs leave sequences behind; resync so ORM inserts work.
        db.execute(text("SELECT setval(pg_get_serial_sequence('teams','id'), (SELECT max(id) FROM teams))"))
        db.execute(text("SELECT setval(pg_get_serial_sequence('matches','id'), (SELECT max(id) FROM matches))"))
        db.execute(text("SELECT setval(pg_get_serial_sequence('leagues','id'), (SELECT max(id) FROM leagues))"))
        for code, (slug, year, name, country) in LEAGUES.items():
            if only and code not in only:
                continue
            lg = db.query(League).filter_by(code=code).first()
            if not lg:
                lg = League(code=code, name=name, country=country, provider="espn",
                            provider_league_id=slug, season="2026")
                db.add(lg)
                db.flush()
                print(f"created league {code}", flush=True)
            season = get(f"{BASE}/leagues/{slug}/seasons/{year}?lang=en&region=us")
            type_refs = season.get("types", {}).get("items", [])
            for tref in type_refs:
                # events live at {type_url}/events (paginated)
                type_base = tref["$ref"].split("?")[0]
                page = 1
                while True:
                    pdata = get(f"{type_base}/events?lang=en&region=us&limit=200&page={page}")
                    items = pdata.get("items", [])
                    if not items:
                        break
                    print(f"{code} {type_base.split('/')[-2]}:{type_base.split('/')[-1]} page={page} events={len(items)} added={added}", flush=True)
                    items = pdata.get("items", [])
                    if not items:
                        break
                    for it in items:
                        ev = get(it["$ref"])
                        eid = str(ev.get("id"))
                        pid = f"espn_{slug}_{eid}"
                        existing = db.query(Match).filter_by(provider_match_id=pid).first()
                        comps = ev.get("competitions") or {}
                        if isinstance(comps, list):
                            comp_ref = (comps[0].get("$ref") if comps else None)
                        else:
                            comp_ref = (comps.get("items", [{}])[0].get("$ref"))
                        if not comp_ref:
                            skipped += 1
                            continue
                        comp = get(comp_ref)
                        competitors = comp.get("competitors") or []
                        if isinstance(competitors, dict):
                            competitors = competitors.get("items", [])
                        if len(competitors) != 2:
                            skipped += 1
                            continue
                        sides = []
                        for c in competitors:
                            cdata = get(c["$ref"]) if "$ref" in c and "score" not in c else c
                            tdata2 = get(cdata["team"]["$ref"])
                            sc = resolve_score(cdata)
                            sides.append({"team_id": str(tdata2.get("id")),
                                          "name": tdata2.get("displayName") or tdata2.get("name"),
                                          "abbr": tdata2.get("abbreviation") or "",
                                          "home": (cdata.get("homeAway") == "home") or bool(cdata.get("isHome", False)),
                                          "score": sc})
                        home = next((s for s in sides if s["home"]), sides[0])
                        away = next((s for s in sides if not s["home"]), sides[1])
                        st = comp.get("status") or {}
                        if isinstance(st, dict) and "$ref" in st and "name" not in st.get("type", {}):
                            st = get(st["$ref"])
                        st_type = st.get("type", {}) if isinstance(st, dict) else {}
                        if isinstance(st_type, dict) and "$ref" in st_type and "name" not in st_type:
                            st_type = get(st_type["$ref"])
                        st_name = st_type.get("name", "") if isinstance(st_type, dict) else ""
                        status, minute = map_status(st_name)
                        ko = datetime.fromisoformat(ev.get("date").replace("Z", "+00:00"))
                        ht = resolve_team(db, lg.id, home["team_id"], home["name"], home["abbr"])
                        at = resolve_team(db, lg.id, away["team_id"], away["name"], away["abbr"])
                        # finished with unknown score: keep scores NULL honestly
                        if existing:
                            # Authoritative ESPN re-sync: overwrite status/scores.
                            existing.status = status
                            existing.minute = minute
                            existing.home_score = home["score"]
                            existing.away_score = away["score"]
                            existing.home_team_id = ht.id
                            existing.away_team_id = at.id
                            skipped += 1
                            continue
                        db.add(Match(league_id=lg.id, home_team_id=ht.id, away_team_id=at.id,
                                     kickoff_at=ko, status=status, minute=minute,
                                     home_score=home["score"], away_score=away["score"],
                                     provider="espn", provider_match_id=pid))
                        added += 1
                        if added % 50 == 0:
                            db.commit()
                            print(f"... {code} added={added} skipped={skipped}", flush=True)
                    if page >= int(pdata.get("pageCount", 1)):
                        break
                    page += 1
            db.commit()
            print(f"{code}: done (added={added} skipped={skipped})", flush=True)
        print(f"TOTAL added={added} skipped={skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
