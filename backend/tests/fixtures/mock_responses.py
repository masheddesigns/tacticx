"""Mocked API-Football /fixtures response (2 fixtures). No live calls."""
FIXTURES_RESPONSE = {
    "response": [
        {
            "fixture": {"id": 12345, "date": "2025-05-01T18:00:00+00:00",
                        "status": {"short": "NS", "elapsed": None}},
            "league": {"id": 39, "name": "Premier League"},
            "teams": {"home": {"id": 42, "name": "Arsenal"},
                      "away": {"id": 49, "name": "Chelsea"}},
            "goals": {"home": None, "away": None},
            "score": {},
        },
        {
            "fixture": {"id": 12346, "date": "2025-05-02T20:00:00+00:00",
                        "status": {"short": "NS", "elapsed": None}},
            "league": {"id": 39, "name": "Premier League"},
            "teams": {"home": {"id": 50, "name": "Man City"},
                      "away": {"id": 51, "name": "Liverpool"}},
            "goals": {"home": None, "away": None},
            "score": {},
        },
    ]
}

ODDS_RESPONSE = [
    {
        "commence_time": "2025-05-01T18:00:00Z",
        "bookmakers": [
            {"key": "bet365", "title": "Bet365", "last_update": "2025-04-30T18:00:00Z",
             "markets": [
                 {"key": "h2h",
                  "outcomes": [{"name": "Home", "price": 1.80},
                               {"name": "Draw", "price": 3.60},
                               {"name": "Away", "price": 4.50}]},
             ]},
        ],
    }
]
