import ast
import json
import os
import re
import sqlite3

def norm(name):
    n = name.lower()
    for word in ['hotspur', 'city', 'united', 'fc', 'sc', 'cf', 'afc', 'borussia', 'vfb', '1.', 'de la plata', 'de río cuarto', 'la coruna', 'club', 'deportivo', 'santiago del estero']:
        n = re.sub(r'\b' + re.escape(word) + r'\b', '', n)
    n = n.replace("nott'm", "nottingham").replace("man ", "manchester ").replace("ein ", "eintracht ").replace('ath ', 'atlético ')
    n = re.sub(r'[^a-z0-9]', '', n)
    return n

def main():
    print("=== Synchronizing Sunday Nov 22 Match Data & Saturday Final Scores ===")

    with open('backend/scripts/espn_live_fetched_nov22.json') as f:
        espn_events = json.load(f)

    # 1. Load seed file
    with open('backend/scripts/seed_full_november_fixtures.py') as f:
        seed_code = f.read()

    prefix_end = seed_code.find('    fixtures = [')
    suffix_start = seed_code.find('    inserted = 0\n    for f in fixtures:')
    if prefix_end == -1 or suffix_start == -1:
        raise ValueError("Could not find fixtures slice boundaries in seed file")

    fixtures_code = seed_code[prefix_end + 4:suffix_start].strip()
    fixtures = ast.literal_eval(fixtures_code[fixtures_code.find('['):])
    print(f"Loaded {len(fixtures)} existing fixtures from seed file.")

    existing_map = {}
    for f in fixtures:
        d = f['date'][:10]
        h = norm(f['home'])
        a = norm(f['away'])
        existing_map[(d, h, a)] = f

    merged_count = 0
    added_count = 0

    for dt_str, ev_list in espn_events.items():
        for ev in ev_list:
            d = ev['date'][:10] if ev.get('date') else f'{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}'
            h_orig = ev['home']
            a_orig = ev['away']
            if not h_orig or not a_orig:
                continue
            h = norm(h_orig)
            a = norm(a_orig)
            
            raw_st = ev['status']
            if 'FULL_TIME' in raw_st or 'FINAL' in raw_st:
                st = 'FINISHED'
            elif 'HALF' in raw_st or 'SECOND' in raw_st or 'FIRST' in raw_st or 'IN_PROGRESS' in raw_st:
                st = 'LIVE'
            else:
                st = 'SCHEDULED'

            target = existing_map.get((d, h, a))
            if not target:
                for (ed, eh, ea), ef in existing_map.items():
                    if ed == d and (h in eh or eh in h) and (a in ea or ea in a):
                        target = ef
                        break

            if target:
                target['status'] = st
                if ev.get('home_score') is not None:
                    target['home_score'] = ev['home_score']
                if ev.get('away_score') is not None:
                    target['away_score'] = ev['away_score']
                merged_count += 1
            else:
                new_f = {
                    'date': ev.get('date') or f'{d}T20:00:00Z',
                    'league': ev.get('league_id', 15),
                    'home': h_orig,
                    'away': a_orig,
                    'status': st,
                    'home_score': ev.get('home_score'),
                    'away_score': ev.get('away_score'),
                    'p_id': f'espn_{ev.get("event_id")}'
                }
                fixtures.append(new_f)
                existing_map[(d, h, a)] = new_f
                added_count += 1

    fixtures.sort(key=lambda x: (x['date'], x.get('league', 0), x['home']))
    print(f"Total fixtures after merging: {len(fixtures)} (Merged: {merged_count}, Added: {added_count})")

    # 2. Save seed_full_november_fixtures.py
    fixtures_lines = ['    fixtures = [']
    for fx in fixtures:
        hs_repr = fx['home_score'] if fx['home_score'] is not None else 'None'
        as_repr = fx['away_score'] if fx['away_score'] is not None else 'None'
        fixtures_lines.append(
            f'        {{"date": "{fx["date"]}", "league": {fx["league"]}, "home": "{fx["home"]}", "away": "{fx["away"]}", "status": "{fx["status"]}", "home_score": {hs_repr}, "away_score": {as_repr}, "p_id": "{fx["p_id"]}"}},'
        )
    fixtures_lines.append('    ]')

    prefix = seed_code[:prefix_end]
    new_code = prefix + '\n'.join(fixtures_lines) + '\n\n' + seed_code[suffix_start:]
    ast.parse(new_code)
    with open('backend/scripts/seed_full_november_fixtures.py', 'w') as f:
        f.write(new_code)
    print("Saved backend/scripts/seed_full_november_fixtures.py cleanly.")

    # 3. Save november_matches_cache.json
    cache_by_date = {}
    for fx in fixtures:
        d_key = fx['date'][:10]
        cache_by_date.setdefault(d_key, []).append(fx)

    with open('backend/scripts/november_matches_cache.json', 'w') as f:
        json.dump(cache_by_date, f, indent=2)
    print("Saved backend/scripts/november_matches_cache.json")

    # 4. Update SQLite backend/dev.db
    conn = sqlite3.connect('backend/dev.db')
    cur = conn.cursor()

    updated_db_matches = 0
    for fx in fixtures:
        d_str = fx['date'][:10]
        h_name = fx['home']
        a_name = fx['away']
        st = fx['status']
        hs = fx['home_score']
        as_ = fx['away_score']
        minute = 90 if st == 'FINISHED' else (45 if st == 'LIVE' else None)

        p_id = fx.get('p_id')
        cur.execute("SELECT id FROM matches WHERE provider_match_id = ?", (p_id,))
        row = cur.fetchone()
        match_id = row[0] if row else None

        if not match_id:
            h_norm = norm(h_name)
            a_norm = norm(a_name)
            cur.execute("""
                SELECT m.id, th.name, ta.name 
                FROM matches m 
                JOIN teams th ON m.home_team_id = th.id 
                JOIN teams ta ON m.away_team_id = ta.id 
                WHERE m.kickoff_at LIKE ?
            """, (f"{d_str}%",))
            for mid, db_h, db_a in cur.fetchall():
                if (norm(db_h) in h_norm or h_norm in norm(db_h)) and (norm(db_a) in a_norm or a_norm in norm(db_a)):
                    match_id = mid
                    break

        if match_id:
            cur.execute("""
                UPDATE matches 
                SET status = ?, home_score = ?, away_score = ?, minute = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (st, hs, as_, minute, match_id))
            updated_db_matches += 1

    conn.commit()
    conn.close()
    print(f"Updated SQLite dev.db successfully: {updated_db_matches} matches updated.")

if __name__ == '__main__':
    main()
