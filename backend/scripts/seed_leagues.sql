-- Seed the 6 configured leagues so the API is usable before first sync.
INSERT INTO leagues (code, name, provider, provider_league_id, season) VALUES
 ('EPL','Premier League','api_football','39','2024'),
 ('LA_LIGA','La Liga','api_football','140','2024'),
 ('SERIE_A','Serie A','api_football','135','2024'),
 ('BUNDESLIGA','Bundesliga','api_football','78','2024'),
 ('LIGUE_1','Ligue 1','api_football','61','2024'),
 ('UCL','UEFA Champions League','api_football','2','2024')
ON CONFLICT DO NOTHING;
