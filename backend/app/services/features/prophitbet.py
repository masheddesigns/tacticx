"""ProphitBet-inspired Weighted Rolling Form & H2H Statistical Engine.

Implements the core machine learning feature engineering from ProphitBet:
1. Exponentially-weighted rolling team form (decaying match recency).
2. Head-to-Head (H2H) historical matchup edge vectors.
3. Goal momentum (recent goals scored / conceded vs season averages).
4. Venue-specific form factors (home attack intensity vs away defensive resistance).
5. Calibrated bivariate goal expectation lambdas for Poisson / Dixon-Coles models.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models.core import Match, Team, MatchStatistic
from app.db.models.enums import MatchStatus
from app.services.predictions.math_utils import score_grid, markets_from_grid


def compute_kelly_stake(probability: float, decimal_odds: float, bankroll_fraction: float = 0.25) -> Dict[str, float]:
    """Compute optimal bankroll fraction using Kelly Criterion (Quarter-Kelly by default).
    
    Formula:
      b = odds - 1
      q = 1 - p
      full_kelly = (b * p - q) / b = (p * odds - 1) / (odds - 1)
      fractional_kelly = full_kelly * bankroll_fraction
    """
    if decimal_odds <= 1.0 or probability <= 0.0 or probability >= 1.0:
        return {"ev_pct": 0.0, "full_kelly": 0.0, "kelly_fraction": 0.0, "recommended_units": 0.0}
    
    ev_pct = round(((probability * decimal_odds) - 1.0) * 100.0, 1)
    b = decimal_odds - 1.0
    q = 1.0 - probability
    full_kelly = (b * probability - q) / b
    
    if full_kelly <= 0:
        return {"ev_pct": ev_pct, "full_kelly": 0.0, "kelly_fraction": 0.0, "recommended_units": 0.0}
    
    fractional_kelly = full_kelly * bankroll_fraction
    # Standard unit sizing for 100u bankroll: min 0.5u, max 3.0u
    recommended_units = round(max(0.5, min(3.0, fractional_kelly * 20.0)), 1)
    return {
        "ev_pct": ev_pct,
        "full_kelly": round(full_kelly, 4),
        "kelly_fraction": round(fractional_kelly, 4),
        "recommended_units": recommended_units,
    }


class ProphitBetFeatureEngine:
    """Engine computing ProphitBet rolling form and H2H momentum metrics."""

    def __init__(self, recency_decay: float = 0.04, min_matches: int = 2):
        self.recency_decay = recency_decay
        self.min_matches = min_matches

    def compute_team_rolling_form(
        self, db: Session, team_id: int, cutoff: Optional[datetime] = None, max_matches: int = 5
    ) -> Dict[str, float]:
        """Compute exponentially weighted rolling form over recent finished matches."""
        cutoff = cutoff or datetime.now(timezone.utc)
        
        # Query pre-cutoff finished matches involving team
        matches = (
            db.query(Match)
            .filter((Match.home_team_id == team_id) | (Match.away_team_id == team_id))
            .filter(Match.status == MatchStatus.FINISHED.value)
            .filter(Match.kickoff_at <= cutoff)
            .order_by(Match.kickoff_at.desc())
            .limit(max_matches)
            .all()
        )

        if not matches:
            return {
                "weighted_points": 1.4,
                "weighted_scored": 1.3,
                "weighted_conceded": 1.2,
                "momentum_index": 1.0,
                "win_streak": 0,
                "unbeaten_streak": 0,
                "sample_size": 0,
            }

        total_weight = 0.0
        weighted_points = 0.0
        weighted_scored = 0.0
        weighted_conceded = 0.0
        win_streak = 0
        unbeaten_streak = 0
        streak_active = True

        for idx, m in enumerate(matches):
            is_home = (m.home_team_id == team_id)
            gf = m.home_score if is_home else m.away_score
            ga = m.away_score if is_home else m.home_score
            if gf is None or ga is None:
                continue

            # Exponential decay weight: w = exp(-decay * days_ago) or rank decay
            age_days = (cutoff - m.kickoff_at).total_seconds() / 86400.0 if m.kickoff_at else idx * 4.0
            weight = math.exp(-self.recency_decay * max(0.0, age_days))
            total_weight += weight

            # Points: Win=3, Draw=1, Loss=0
            if gf > ga:
                pts = 3.0
                if streak_active:
                    win_streak += 1
                    unbeaten_streak += 1
            elif gf == ga:
                pts = 1.0
                if streak_active:
                    unbeaten_streak += 1
                    streak_active = False
            else:
                pts = 0.0
                streak_active = False

            weighted_points += pts * weight
            weighted_scored += gf * weight
            weighted_conceded += ga * weight

        denom = max(0.001, total_weight)
        avg_pts = weighted_points / denom
        avg_scored = weighted_scored / denom
        avg_conceded = weighted_conceded / denom

        # Momentum index: > 1.0 means team is outperforming historical baseline
        momentum = max(0.6, min(1.8, (avg_pts / 1.5) * (avg_scored / max(0.8, avg_conceded))))

        return {
            "weighted_points": round(avg_pts, 2),
            "weighted_scored": round(avg_scored, 2),
            "weighted_conceded": round(avg_conceded, 2),
            "momentum_index": round(momentum, 2),
            "win_streak": win_streak,
            "unbeaten_streak": unbeaten_streak,
            "sample_size": len(matches),
        }

    def compute_head_to_head_bias(
        self, db: Session, home_id: int, away_id: int, cutoff: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Compute H2H historical edge and scoring rate between the two teams."""
        cutoff = cutoff or datetime.now(timezone.utc)
        meetings = (
            db.query(Match)
            .filter(
                ((Match.home_team_id == home_id) & (Match.away_team_id == away_id))
                | ((Match.home_team_id == away_id) & (Match.away_team_id == home_id))
            )
            .filter(Match.status == MatchStatus.FINISHED.value)
            .filter(Match.kickoff_at <= cutoff)
            .order_by(Match.kickoff_at.desc())
            .limit(6)
            .all()
        )

        if not meetings:
            return {"h2h_home_edge": 0.0, "h2h_avg_goals": 2.6, "h2h_sample": 0}

        home_points = 0.0
        total_goals = 0.0
        for m in meetings:
            is_home_actual = (m.home_team_id == home_id)
            h_g = m.home_score if is_home_actual else m.away_score
            a_g = m.away_score if is_home_actual else m.home_score
            if h_g is None or a_g is None:
                continue
            total_goals += (h_g + a_g)
            if h_g > a_g:
                home_points += 3.0
            elif h_g == a_g:
                home_points += 1.0

        n = len(meetings)
        home_edge = (home_points / (n * 3.0)) - 0.5  # Positive = home dominates, Negative = away dominates
        return {
            "h2h_home_edge": round(max(-0.4, min(0.4, home_edge)), 2),
            "h2h_avg_goals": round(total_goals / n, 2),
            "h2h_sample": n,
        }

    def calibrate_lambdas_and_probabilities(
        self,
        db: Session,
        home_id: int,
        away_id: int,
        base_lam_h: float = 1.45,
        base_lam_a: float = 1.15,
        cutoff: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Apply ProphitBet rolling form and H2H weights to calibrate Poisson lambdas."""
        home_form = self.compute_team_rolling_form(db, home_id, cutoff=cutoff)
        away_form = self.compute_team_rolling_form(db, away_id, cutoff=cutoff)
        h2h = self.compute_head_to_head_bias(db, home_id, away_id, cutoff=cutoff)

        # ProphitBet multiplicative adjustments
        h_mom = home_form["momentum_index"]
        a_mom = away_form["momentum_index"]
        h2h_edge = h2h["h2h_home_edge"]

        # Attack strength vs opponent defense resistance
        lam_h_adj = base_lam_h * (1.0 + 0.12 * (h_mom - 1.0) + 0.10 * h2h_edge + 0.08 * (home_form["weighted_scored"] - 1.2))
        lam_a_adj = base_lam_a * (1.0 + 0.12 * (a_mom - 1.0) - 0.10 * h2h_edge + 0.08 * (away_form["weighted_scored"] - 1.1))

        # Home venue advantage (standard +0.15 goals)
        lam_h = round(max(0.45, min(4.2, lam_h_adj)), 2)
        lam_a = round(max(0.35, min(3.8, lam_a_adj)), 2)

        # Generate bivariate Poisson probability grid with Dixon-Coles low-score correction (rho=-0.13)
        grid = score_grid(lam_h, lam_a, max_goals=9, dixon_coles_rho=-0.13)
        mkts = markets_from_grid(grid)

        p_h = mkts["home_win_probability"]
        p_d = mkts["draw_probability"]
        p_a = mkts["away_win_probability"]
        p_o15 = mkts["over_1_5_probability"]
        p_o25 = mkts["over_2_5_probability"]
        p_o35 = mkts["over_3_5_probability"]
        p_btts = mkts["btts_yes_probability"]

        return {
            "lam_h": lam_h,
            "lam_a": lam_a,
            "p_h": round(p_h, 4),
            "p_d": round(p_d, 4),
            "p_a": round(p_a, 4),
            "p_o15": round(p_o15, 4),
            "p_o25": round(p_o25, 4),
            "p_o35": round(p_o35, 4),
            "p_btts": round(p_btts, 4),
            "home_form": home_form,
            "away_form": away_form,
            "h2h": h2h,
        }
