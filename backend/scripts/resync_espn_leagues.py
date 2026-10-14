"""Fast parallel ESPN re-sync for backfilled leagues (MLS/ISL/LIGA_ARG/BRA_SERIE_A).

Self-contained. Re-fetches every event (parallel fetch phase), then upserts
status/scores/teams authoritatively (serial DB phase). Idempotent.
Usage: python /tmp/resync_backfill.py [MLS ISL LIGA_ARG BRA_SERIE_A]
"""
import concurrent.futures
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

from app.db.models.core import League, Match, Team
from app.db.session import get_session_local
from app.services.match_progression import _teams_match

BASE = "https://sports.core.api.espn.com/v2/sports/soccer"
LEAGUES = {
    "MLS": ("usa.1", 2026, "Major League Soccer", "USA"),
    "UEL": ("uefa.europa", 2026, "UEFA Europa League", "Europe"),
    "UECL": ("uefa.europa.conf", 2026, "UEFA Conference League", "Europe"),
    "ISL": ("ind.1", 2026, "Indian Super League", "India"),
    "LIGA_ARG": ("arg.1", 2026, "Liga Profesional Argentina", "Argentina"),
    "BRA_SERIE_A": ("bra.1", 2026, "Brasileirao Serie A", "Brazil"),
}
WORKERS = 12
_cache: dict = {}


def get(url):
    if url in _cache:
        return _cache[url]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode())
            _cache[url] = data
            return data
        except Exception as e:  # noqa: BLE001
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


def fetch_event(args):
    code, slug, eid = args
    try:
        ev = get(f"{BASE}/leagues/{slug}/events/{eid}?lang=en&region=us")
        comps = ev.get("competitions") or []
        comp_ref = comps[0].get("$ref") if comps else None
        if not comp_ref:
            return None
        comp = get(comp_ref)
        competitors = comp.get("competitors") or []
        if isinstance(competitors, dict):
            competitors = competitors.get("items", [])
        if len(competitors) != 2:
            return None
        sides = []
        for c in competitors:
            cdata = get(c["$ref"]) if "$ref" in c and "score" not in c else c
            tdata = get(cdata["team"]["$ref"])
            sides.append({
                "team_id": str(tdata.get("id")),
                "name": tdata.get("displayName") or tdata.get("name"),
                "abbr": tdata.get("abbreviation") or "",
                "home": (cdata.get("homeAway") == "home") or bool(cdata.get("isHome", False)),
                "score": resolve_score(cdata),
            })
        st = comp.get("status") or {}
        if isinstance(st, dict) and "$ref" in st and "name" not in st.get("type", {}):
            st = get(st["$ref"])
        st_type = st.get("type", {}) if isinstance(st, dict) else {}
        if isinstance(st_type, dict) and "$ref" in st_type and "name" not in st_type:
            st_type = get(st_type["$ref"])
        status, minute = map_status(st_type.get("name", "") if isinstance(st_type, dict) else "")
        home = next((s for s in sides if s["home"]), sides[0])
        away = next((s for s in sides if not s["home"]), sides[1])
        return {"pid": f"espn_{slug}_{eid}", "code": code,
                "status": status, "minute": minute, "home": home, "away": away}
    except Exception as e:  # noqa: BLE001
        return {"pid": f"espn_{slug}_{eid}", "error": str(e)[:100]}


def resolve_team(db, league_id, espn_team_id, display, abbr):
    existing = db.query(Team).filter_by(
        provider="espn", provider_team_id=f"espn-{espn_team_id}").first()
    if existing:
        return existing
    for t in db.query(Team).filter(Team.league_id == league_id).all():
        if _teams_match(t.name, display) or (abbr and _teams_match(t.name, abbr)):
            return t
    t = Team(league_id=league_id, name=display, short_name=(abbr or display)[:32],
             country="", provider="espn", provider_team_id=f"espn-{espn_team_id}")
    db.add(t)
    db.flush()
    return t


def main():
    only = set(a.upper() for a in sys.argv[1:]) or None
    db = get_session_local()()
    try:
        jobs = []
        for code, (slug, _y, _n, _c) in LEAGUES.items():
            if only and code not in only:
                continue
            eids = [r[0].split(f"espn_{slug}_")[1] for r in
                    db.query(Match.provider_match_id)
                    .filter(Match.provider_match_id.like(f"espn_{slug}\\_%"))
                    .all()]
            jobs += [(code, slug, eid) for eid in eids]
        print(f"events to resync: {len(jobs)}", flush=True)
        payloads = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for i, payload in enumerate(pool.map(fetch_event, jobs)):
                payloads.append(payload)
                if (i + 1) % 200 == 0:
                    print(f"fetched {i + 1}/{len(jobs)}", flush=True)
        updated = errors = fixed_teams = 0
        for payload in payloads:
            if not payload or "error" in payload:
                errors += 1
                continue
            m = db.query(Match).filter_by(provider_match_id=payload["pid"]).first()
            if not m:
                continue
            lg = db.query(League).filter_by(code=payload["code"]).first()
            ht = resolve_team(db, lg.id, payload["home"]["team_id"],
                              payload["home"]["name"], payload["home"]["abbr"])
            at = resolve_team(db, lg.id, payload["away"]["team_id"],
                              payload["away"]["name"], payload["away"]["abbr"])
            if m.home_team_id != ht.id or m.away_team_id != at.id:
                fixed_teams += 1
            m.status = payload["status"]
            m.minute = payload["minute"]
            m.home_score = payload["home"]["score"]
            m.away_score = payload["away"]["score"]
            m.home_team_id = ht.id
            m.away_team_id = at.id
            updated += 1
            if updated % 100 == 0:
                db.commit()
        db.commit()
        print(f"TOTAL updated={updated} team_fixes={fixed_teams} errors={errors}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
