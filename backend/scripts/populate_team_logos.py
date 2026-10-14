"""Populate teams.logo_url from ESPN CDN (verified per-team).

Only saves URLs that return HTTP 200 + image content-type. Idempotent:
skips teams that already have a logo_url. Run inside scheduler container:
    docker cp populate_team_logos.py tacticx-local-scheduler:/tmp/ && \
    docker exec tacticx-local-scheduler python /tmp/populate_team_logos.py
"""
import concurrent.futures
import urllib.request

from app.db.models.core import Team
from app.db.session import get_session_local

WORKERS = 12


def check(team_row):
    tid, espn_id = team_row
    url = f"https://a.espncdn.com/i/teamlogos/soccer/500/{espn_id}.png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200 and "image" in (resp.headers.get("Content-Type") or "")
        return tid, url if ok else None
    except Exception:  # noqa: BLE001 - keep NULL honestly on any failure
        return tid, None


def main():
    db = get_session_local()()
    try:
        rows = [(t.id, t.provider_team_id.replace("espn-", "", 1))
                for t in db.query(Team).filter(Team.provider == "espn",
                                               Team.logo_url.is_(None)).all()
                if (t.provider_team_id or "").startswith("espn-")]
        print(f"teams to verify: {len(rows)}", flush=True)
        saved = failed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for tid, url in pool.map(check, rows):
                if url:
                    db.query(Team).filter_by(id=tid).update({"logo_url": url})
                    saved += 1
                else:
                    failed += 1
                if (saved + failed) % 100 == 0:
                    db.commit()
        db.commit()
        print(f"TOTAL saved={saved} failed={failed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
