"""Resolve ESPN numeric IDs + logos for underscore-format espn team rows.

For each logo-less espn team, finds one of its matches, pulls the ESPN site
scoreboard for that date/league, matches the event by team names, and stores
the ESPN numeric team id + verified CDN logo URL. Run in scheduler container.
"""
import json
import urllib.request

from app.db.models.core import League, Match, Team
from app.db.session import get_session_local
from app.services.match_progression import _teams_match

SLUGS = {6: "uefa.champions", 2: "esp.1", 3: "ita.1", 9: "usa.1", 10: "ind.1",
         11: "arg.1", 12: "bra.1", 1: "eng.1", 4: "ger.1", 5: "fra.1",
         13: "uefa.europa", 14: "uefa.europa.conf"}


def fetch(date_str, slug):
    url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
           f"{slug}/scoreboard?dates={date_str}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode()).get("events", [])


def head_ok(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200 and "image" in (resp.headers.get("Content-Type") or "")
    except Exception:  # noqa: BLE001
        return False


def main():
    db = get_session_local()()
    try:
        targets = db.query(Team).filter(Team.provider == "espn", Team.logo_url.is_(None)).all()
        print(f"targets: {len(targets)}", flush=True)
        fixed = 0
        for t in targets:
            candidates = db.query(Match).filter(
                (Match.home_team_id == t.id) | (Match.away_team_id == t.id)
            ).order_by(Match.kickoff_at).all()
            for m in candidates:
                if t.logo_url:
                    break
                if not m or not m.kickoff_at:
                    continue
                slug = SLUGS.get(m.league_id)
                if not slug:
                    continue
                date_str = m.kickoff_at.strftime("%Y%m%d")
                other_id = m.away_team_id if m.home_team_id == t.id else m.home_team_id
                other = db.get(Team, other_id)
                try:
                    events = fetch(date_str, slug)
                except Exception:  # noqa: BLE001
                    continue
                print(f"DBG {t.name} m={m.id} ds={date_str} slug={slug} nev={len(events)}", flush=True)
                for ev in events:
                    comp = (ev.get("competitions") or [{}])[0]
                    cs = comp.get("competitors", [])
                    if len(cs) != 2:
                        continue
                    home_c = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
                    away_c = next((c for c in cs if c.get("homeAway") == "away"), cs[1])
                    hn = ((home_c.get("team") or {}).get("displayName") or "")
                    an = ((away_c.get("team") or {}).get("displayName") or "")
                    mine = hn if m.home_team_id == t.id else an
                    theirs = an if m.home_team_id == t.id else hn
                    print(f"DBG ev: mine={mine!r} theirs={theirs!r} vs {t.name!r}/{other.name if other else None!r}", flush=True)
                    if _teams_match(mine, t.name) and (not other or _teams_match(theirs, other.name)):
                        espn_id = ((home_c if m.home_team_id == t.id else away_c).get("team") or {}).get("id")
                        if espn_id:
                            url = f"https://a.espncdn.com/i/teamlogos/soccer/500/{espn_id}.png"
                            if head_ok(url):
                                t.provider_team_id = f"espn-{espn_id}"
                                t.logo_url = url
                                fixed += 1
                                print(f"fixed {t.name} -> espn-{espn_id}", flush=True)
                        break
        db.commit()
        print(f"TOTAL fixed={fixed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
