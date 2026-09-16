"""File-based historical dataset source (Phase 1.6).

Bulk path for model training / backtesting: local CSV / JSON / JSONL files
(Parquet when an engine is installed). Auto-detects two schemas:

- football-data.co.uk columns: Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR (+HT..,
  closing odds B365H/B365D/B365A, B365>2.5/B365<2.5, other bookmakers...)
- generic columns: date,home_team,away_team,home_score,away_score (+kickoff,
  league,season,status,result,...)

Custom layouts via --column-map. Every row keeps its source record ID and
parser version; malformed rows are collected with reasons, never silently
discarded.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from typing import Optional

from app.logging_config import get_logger
from app.services.sources.base import (
    FootballDataSource,
    HistoricalDataSource,
    OddsDataSource,
    SourceCapabilities,
)
from app.services.sources.normalized import (
    NormalizedMatch,
    NormalizedMatchStatistics,
    NormalizedOddsSelection,
    NormalizedOddsSnapshot,
    NormalizedTeam,
    Provenance,
)

log = get_logger(__name__)

PARSER = "csv_dataset_parser_v1"

# football-data.co.uk division codes -> our league codes (for the league filter).
DIV_TO_LEAGUE = {
    "E0": "EPL", "SP1": "LA_LIGA", "I1": "SERIE_A",
    "D1": "BUNDESLIGA", "F1": "LIGUE_1",
}


def league_matches(row_league: str, wanted: str) -> bool:
    """True when a row's competition tag refers to the wanted league code."""
    if not row_league or not wanted:
        return True  # untagged rows are scoped by the caller's league/season
    rl, w = row_league.strip(), wanted.strip()
    return rl.lower() == w.lower() or DIV_TO_LEAGUE.get(rl.upper(), "") == w.upper()


# football-data.co.uk bookmaker column prefixes -> (display name, provider id).
BOOKMAKERS = {
    "B365": ("Bet365", "b365"),
    "BS": ("Blue Square", "blue_square"),
    "BW": ("Betway", "betway"),
    "GB": ("Gamebookers", "gamebookers"),
    "IW": ("Interwetten", "interwetten"),
    "LB": ("Ladbrokes", "ladbrokes"),
    "PS": ("Pinnacle", "pinnacle"),
    "SO": ("Sporting Odds", "sporting_odds"),
    "SB": ("Sportingbet", "sportingbet"),
    "SJ": ("Stan James", "stan_james"),
    "SY": ("Stanleybet", "stanleybet"),
    "VC": ("Bet Victor", "bet_victor"),
    "WH": ("William Hill", "william_hill"),
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M")


def parse_date(value: object) -> Optional[datetime]:
    """Parse common football-dataset date shapes. None when unparseable."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:  # ISO first (handles offsets)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc) if "%H" not in fmt or dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _num(value: object) -> Optional[float]:
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def _int(value: object) -> Optional[int]:
    num = _num(value)
    return int(num) if num is not None and num.is_integer() else None


class RowIssue(Exception):
    pass


def canonical_row(raw: dict, column_map: Optional[dict] = None) -> dict:
    """Map one raw row to canonical keys. Raises RowIssue listing problems."""
    cmap = column_map or {}
    is_fd = "HomeTeam" in raw and "AwayTeam" in raw  # football-data.co.uk shape

    def pick(*names: str) -> object:
        for name in names:
            mapped = cmap.get(name, name)
            if mapped in raw and raw[mapped] not in (None, ""):
                return raw[mapped]
        return None

    if is_fd:
        date_v = pick("Date")
        time_v = pick("Time")
        if date_v is not None and time_v is not None:
            # Kickoff precision matters for cross-source match identity.
            date_v = f"{date_v} {time_v}".strip()
        home = pick("HomeTeam")
        away = pick("AwayTeam")
        hs = _int(pick("FTHG"))
        as_ = _int(pick("FTAG"))
    else:
        date_v = pick("date", "Date", "kickoff", "match_date")
        home = pick("home", "home_team", "HomeTeam", "homeTeam")
        away = pick("away", "away_team", "AwayTeam", "awayTeam")
        hs = _int(pick("home_score", "hs", "FTHG", "homeScore", "goals_home"))
        as_ = _int(pick("away_score", "as", "FTAG", "awayScore", "goals_away"))

    problems = []
    if home is None:
        problems.append("missing home team")
    if away is None:
        problems.append("missing away team")
    kickoff = parse_date(date_v)
    if date_v is not None and kickoff is None:
        problems.append(f"unparseable date: {date_v!r}")
    if problems:
        raise RowIssue("; ".join(problems))

    row = {
        "date_raw": date_v,
        "kickoff": kickoff,
        "home": str(home).strip(),
        "away": str(away).strip(),
        "home_score": hs,
        "away_score": as_,
        "league": str(pick("league", "Div", "competition") or "").strip(),
        "season": str(pick("season", "Season") or "").strip(),
        "status": str(pick("status", "Status") or "").strip() or ("FINISHED" if hs is not None else "SCHEDULED"),
        "raw": raw,
    }
    if is_fd:
        row["stats"] = _fdco_stats(raw)
    return row


# football-data.co.uk stat column -> (side, canonical stat name, period).
# Only source-provided measurements; NOTHING derived (no off-target math).
FDCO_STAT_COLUMNS = {
    "HS": ("home", "shots_total", "full"),
    "AS": ("away", "shots_total", "full"),
    "HST": ("home", "shots_on_target", "full"),
    "AST": ("away", "shots_on_target", "full"),
    "HC": ("home", "corners", "full"),
    "AC": ("away", "corners", "full"),
    "HF": ("home", "fouls", "full"),
    "AF": ("away", "fouls", "full"),
    "HY": ("home", "yellow_cards", "full"),
    "AY": ("away", "yellow_cards", "full"),
    "HR": ("home", "red_cards", "full"),
    "AR": ("away", "red_cards", "full"),
    "HTHG": ("home", "goals", "1h"),
    "HTAG": ("away", "goals", "1h"),
}


def _fdco_stats(raw: dict) -> dict:
    """Extract per-side stat cells. Empty cells are skipped (missing stays missing)."""
    home: dict = {}
    away: dict = {}
    for col, (side, name, period) in FDCO_STAT_COLUMNS.items():
        value = _int(raw.get(col))
        if value is None:
            continue
        (home if side == "home" else away)[(name, period)] = str(value)
    return {"home": home, "away": away}


def match_stats_from_row(row: dict, source: str,
                         parser_version: str) -> list[NormalizedMatchStatistics]:
    """Normalized per-team statistics from a canonical row. No stats -> []."""
    from app.services.scraping.framework import utcnow

    out: list[NormalizedMatchStatistics] = []
    for side in ("home", "away"):
        for (name, period), value in (row.get("stats") or {}).get(side, {}).items():
            out.append(NormalizedMatchStatistics(
                team=side, stat_name=name, stat_value=value, period=period,
                provenance=Provenance(
                    source=source,
                    source_record_id=f"{row['home']}-v-{row['away']}-{row['kickoff']}:{side}:{name}",
                    collected_at=utcnow(), parser_version=parser_version,
                    temporal_quality="estimated")))
    return out


def _is_midnight(dt) -> bool:
    """Date-only evidence carries midnight; never present it as observed time."""
    try:
        return dt is not None and dt.hour == 0 and dt.minute == 0 and dt.second == 0
    except Exception:  # noqa: BLE001
        return False


def closing_odds_snapshots(row: dict, source: str, league_code: str, season: str,
                           kickoff: Optional[datetime]) -> list[NormalizedOddsSnapshot]:
    """Bookmaker prices from football-data.co.uk odds columns.

    Both opening (B365H...) and closing (B365CH...) lines are stored as
    separate snapshots, distinguished by source_market_id ("b365:h2h" vs
    "b365C:h2h"). Timestamps are the kickoff (the moment a closing price is
    known to have held); temporal_quality="estimated" marks the imprecision.
    collected_at stays None — the true scrape time is unknown, not invented.
    Asian handicap uses the file's AHh line as point; absent -> skipped.
    """
    raw = row["raw"]
    if not isinstance(raw, dict) or "B365H" not in raw:
        return []
    # A midnight kickoff means date-only evidence: stamping it as the price
    # observation time would be false precision. Leave timestamp empty so the
    # pipeline marks import time and the leakage audit flags it honestly.
    ts = None if _is_midnight(kickoff) else kickoff
    out: list[NormalizedOddsSnapshot] = []
    variants = [("", ""), ("C", "C")]  # (column infix, market-id tag)
    for prefix, (bname, bid) in BOOKMAKERS.items():
        for infix, tag in variants:
            h2h = [(_num(raw.get(f"{prefix}{infix}H")), "home", None),
                   (_num(raw.get(f"{prefix}{infix}D")), "draw", None),
                   (_num(raw.get(f"{prefix}{infix}A")), "away", None)]
            totals = [(_num(raw.get(f"{prefix}{infix}>2.5")), "over_2.5", 2.5),
                      (_num(raw.get(f"{prefix}{infix}<2.5")), "under_2.5", 2.5)]
            ah_line = _num(raw.get("AHh")) if not infix else None
            ah = [(_num(raw.get(f"{prefix}{infix}AHH")), "home", ah_line),
                  (_num(raw.get(f"{prefix}{infix}AHA")), "away", ah_line)]
            markets = [("h2h", h2h), ("totals", totals)]
            if ah_line is not None:
                markets.append(("asian_handicap", ah))
            for market, cells in markets:
                sels = [NormalizedOddsSelection(selection=sel, price=p, point=pt,
                                                bookmaker=bname, bookmaker_id=bid)
                        for p, sel, pt in cells if p is not None and p > 1.0]
                if not sels:
                    continue  # market absent from source -> never invented
                out.append(NormalizedOddsSnapshot(
                    league_code=league_code, season=season,
                    home_team=row["home"], away_team=row["away"], kickoff_at=kickoff,
                    market=market, timestamp=ts, collected_at=None, is_live=False,
                    source=source, source_event_id="",
                    source_market_id=f"{prefix}{tag}:{market}",
                    selections=sels,
                    provenance=Provenance(
                        source=source,
                        source_record_id=f"{row['home']}-v-{row['away']}-{kickoff}:{prefix}{tag}:{market}",
                        collected_at=None, effective_at=kickoff,
                        parser_version="csv_dataset_parser_v1",
                        temporal_quality="estimated")))
    return out


def import_rows(db, source: str, rows: list, league_code: str, season: str,
                column_map: Optional[dict] = None, date_from: Optional[str] = None,
                date_to: Optional[str] = None, create_teams: bool = True,
                parser_version: str = PARSER, rejected_sink: Optional[list] = None,
                rid_prefix: str = "", source_url: str = "") -> dict:
    """Shared bulk-import engine: validate -> resolve -> persist -> report.

    Idempotent and resumable: re-running the same rows yields duplicates/
    updates only, never new rows. Malformed rows go to `rejected_sink`
    (and the invalid count) — never silently discarded.
    """
    from app.services.sources.pipeline import Pipeline


    pipe = Pipeline(db, source, create_teams=create_teams, source_url=source_url)
    league = pipe.ensure_league(league_code, season=season)
    report = {"records_read": 0, "valid": 0, "filtered": 0, "inserted": 0, "updated": 0,
              "duplicates_skipped": 0, "invalid": 0, "errors": []}
    rejected: list[dict] = rejected_sink if rejected_sink is not None else []
    df = parse_date(date_from).date() if date_from else None
    dt = parse_date(date_to).date() if date_to else None

    for idx, raw in enumerate(rows):
        report["records_read"] += 1
        try:
            row = canonical_row(raw if isinstance(raw, dict) else {}, column_map)
        except RowIssue as exc:
            report["invalid"] += 1
            rejected.append({"row": idx, "reason": str(exc), "raw": raw})
            continue
        if not league_matches(row["league"], league_code):
            report["filtered"] += 1
            continue  # other competitions are skipped, not errors
        if row["kickoff"] and ((df and row["kickoff"].date() < df)
                               or (dt and row["kickoff"].date() > dt)):
            report["filtered"] += 1
            continue
        report["valid"] += 1
        rid = f"{rid_prefix}{idx}"
        match = NormalizedMatch(
            league_code=league_code, season=row["season"] or season,
            home_team=row["home"], away_team=row["away"], kickoff_at=row["kickoff"],
            status=row["status"], home_score=row["home_score"], away_score=row["away_score"],
            provider_match_id=rid,
            provenance=Provenance(source=source, source_record_id=rid,
                                  collected_at=row["kickoff"], parser_version=parser_version))
        try:
            match_id = pipe.ingest_match(match, league_id=league.id, parser_version=parser_version)
            if match_id is not None:
                for stat in match_stats_from_row(row, source, parser_version):
                    pipe.ingest_statistics(match_id, [stat], parser_version=parser_version)
                for snap in closing_odds_snapshots(row, source, league_code,
                                                   row["season"] or season, row["kickoff"]):
                    pipe.ingest_odds(snap, parser_version=parser_version)
        except Exception as exc:  # noqa: BLE001 — one bad row never kills the import
            report["errors"].append(f"row {idx}: {exc}"[:200])
    stats = pipe.stats
    report["inserted"] = stats.inserted
    report["updated"] = stats.updated
    report["duplicates_skipped"] = stats.duplicates
    report["invalid"] += stats.quarantined + stats.unresolved
    pipe.finish("import_history", league=league_code)
    report["_rejected"] = rejected
    return report


def read_dataset(path: str) -> tuple[list[dict], str]:
    """Read CSV/JSON/JSONL/Parquet into raw row dicts. Returns (rows, format)."""
    lower = path.lower()
    if lower.endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [dict(r) for r in csv.DictReader(fh)], "csv"
    if lower.endswith((".jsonl", ".ndjson")):
        rows = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
        return rows, "jsonl"
    if lower.endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("matches"), list):
            data = data["matches"]
        if not isinstance(data, list):
            raise ValueError("JSON dataset must be a list (or {'matches': [...]})")
        return [r for r in data if isinstance(r, dict)], "json"
    if lower.endswith((".parquet", ".pq")):
        try:
            import pandas as pd  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "parquet support needs pandas and pyarrow installed (pip install pandas pyarrow)"
            ) from exc
        return pd.read_parquet(path).to_dict(orient="records"), "parquet"
    raise ValueError(f"unsupported dataset format: {path} (use .csv/.json/.jsonl/.parquet)")


class CsvFileSource(HistoricalDataSource, FootballDataSource, OddsDataSource):
    """Local dataset files as a first-class source (bulk import path)."""

    source_name = "csv"
    capabilities = SourceCapabilities(fixtures=True, historical_bulk=True,
                                      odds_prematch=True)

    def __init__(self, file_path: str = "", column_map: Optional[dict] = None,
                 db=None, **kwargs):
        self.file_path = file_path
        self.column_map = column_map or {}
        self.db = db

    def check(self) -> dict:
        import os

        return {"source": self.source_name,
                "file": self.file_path or "(none — pass file_path)",
                "exists": bool(self.file_path) and os.path.exists(self.file_path)}

    # -- bulk import -----------------------------------------------------
    def import_history(self, league_code: str, season: str,
                       date_from: Optional[str] = None, date_to: Optional[str] = None,
                       **kwargs) -> dict:
        if not self.file_path:
            raise ValueError("CsvFileSource needs file_path")
        if self.db is None:
            raise ValueError("CsvFileSource needs db (pass db=session)")
        rows, _ = read_dataset(self.file_path)
        rejected: list = []
        report = import_rows(
            self.db, self.source_name, rows, league_code, season,
            column_map=self.column_map, date_from=date_from, date_to=date_to,
            create_teams=kwargs.get("create_teams", True),
            parser_version=PARSER, rejected_sink=rejected,
            rid_prefix=f"{self.file_path}#", source_url=self.file_path)
        report["_rejected"] = rejected
        return report

    def _prov(self, rid: str):
        from app.services.scraping.framework import utcnow


        return Provenance(source=self.source_name, source_record_id=rid,
                          collected_at=utcnow(), parser_version=PARSER)

    # -- FootballDataSource surface (reads the same file) ----------------
    def _filtered(self, league_code: str, season: str,
                  date_from: Optional[str], date_to: Optional[str]) -> list[tuple[int, dict]]:
        rows, _ = read_dataset(self.file_path)
        out = []
        df = parse_date(date_from).date() if date_from else None
        dt = parse_date(date_to).date() if date_to else None
        for idx, raw in enumerate(rows):
            try:
                row = canonical_row(raw if isinstance(raw, dict) else {}, self.column_map)
            except RowIssue:
                continue
            if row["kickoff"] and ((df and row["kickoff"].date() < df)
                                   or (dt and row["kickoff"].date() > dt)):
                continue
            out.append((idx, row))
        return out

    async def get_leagues(self) -> list[dict]:
        return []

    async def get_teams(self, league_code: str, season: str) -> list[NormalizedTeam]:
        seen: dict[str, NormalizedTeam] = {}
        for _, row in self._filtered(league_code, season, None, None):
            for name in (row["home"], row["away"]):
                if name not in seen:
                    seen[name] = NormalizedTeam(name=name, league_code=league_code,
                                                provenance=self._prov(f"team:{name}"))
        return list(seen.values())

    async def get_fixtures(self, league_code: str, season: str,
                           date_from: Optional[str] = None,
                           date_to: Optional[str] = None) -> list[NormalizedMatch]:
        return [
            NormalizedMatch(
                league_code=league_code, season=row["season"] or season,
                home_team=row["home"], away_team=row["away"], kickoff_at=row["kickoff"],
                status=row["status"], home_score=row["home_score"], away_score=row["away_score"],
                provenance=self._prov(f"row:{idx}"))
            for idx, row in self._filtered(league_code, season, date_from, date_to)
        ]

    async def get_match_statistics(self, source_match_id: str) -> list[NormalizedMatchStatistics]:
        try:
            want = int(str(source_match_id).split(":", 1)[1])
        except (IndexError, ValueError):
            return []
        rows, _ = read_dataset(self.file_path)
        if not 0 <= want < len(rows):
            return []
        try:
            row = canonical_row(rows[want] if isinstance(rows[want], dict) else {},
                                self.column_map)
        except RowIssue:
            return []
        return match_stats_from_row(row, self.source_name, PARSER)

    async def get_match_events(self, source_match_id: str) -> list:
        return []

    async def get_lineups(self, source_match_id: str) -> list:
        return []

    async def get_standings(self, league_code: str, season: str) -> list:
        return []

    async def get_players(self, league_code: str, season: str) -> list:
        return []

    # -- OddsDataSource surface ------------------------------------------
    async def get_odds_snapshots(self, league_code: str = "", season: str = "",
                                 live: bool = False) -> list[NormalizedOddsSnapshot]:
        if live:
            return []  # files hold closing (pre-match) lines only
        out = []
        for _, row in self._filtered(league_code, season, None, None):
            out.extend(closing_odds_snapshots(row, self.source_name, league_code, season,
                                              row["kickoff"]))
        return out

    def supported_markets(self) -> list[str]:
        return ["h2h", "totals"]
