"""Advanced models (Phase 4).

advanced_v1: multinomial logistic regression (softmax) over a small,
fully pre-cutoff feature vector, implemented in numpy only (no sklearn in
this environment). Chosen because the honest training sample is a few
thousand rows with ~6 features — a small regularized linear model is
appropriate; trees/boosting would be unjustified here. Deterministic:
zeros init, fixed row order, full-batch gradient descent, no randomness.

advanced_goal_v1: Poisson goal model with half-life recency, xG blend where
eligible, and documented shrinkage toward the league mean for thin histories
(5-9 matches). Compared chronologically against poisson_v1 / poisson_v1-xg.

calibration_v1: single-temperature scaling on 1X2 logits, fitted on TRAIN
data only via deterministic golden-section search. Never fitted on test
outcomes. Applied through CalibratedModel (version suffix "-cal").
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Match
from app.services.features import engineered as eng
from app.services.features.availability import assess_availability
from app.services.features.repository import HistoricalFeatureRepository
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.predictions.math_utils import markets_from_grid, score_grid
from app.services.predictions.outputs import FullPrediction
from app.services.predictions.poisson import PoissonConfig, PoissonModel, _InsufficientData

MODEL_NAME = "advanced"
MODEL_VERSION = "advanced_v1"
GOAL_MODEL_NAME = "advanced_goal"
GOAL_MODEL_VERSION = "advanced_goal_v1"
CALIBRATION_VERSION = "calibration_v1"

# Fixed feature order. Small on purpose: the honest sample is thousands of
# rows, not millions. xG features exist only in the xg=True configuration.
BASE_FEATURES = ["elo_diff", "form_ppm_diff_5", "gd_diff_5", "rest_diff"]
XG_FEATURES = BASE_FEATURES + ["xg_diff_5"]


@dataclass
class AdvancedConfig:
    use_xg: bool = False
    l2: float = 1.0
    learning_rate: float = 0.5
    iterations: int = 2000
    minimum_team_matches: int = 5
    minimum_xg_matches: int = 5

    @classmethod
    def from_settings(cls, use_xg: bool = False) -> "AdvancedConfig":
        settings = get_settings()
        return cls(use_xg=use_xg, l2=float(settings.ML_L2),
                   learning_rate=float(settings.ML_LEARNING_RATE),
                   iterations=int(settings.ML_ITERATIONS))

    def as_dict(self) -> Dict:
        return {"use_xg": self.use_xg, "l2": self.l2,
                "learning_rate": self.learning_rate, "iterations": self.iterations,
                "minimum_team_matches": self.minimum_team_matches,
                "minimum_xg_matches": self.minimum_xg_matches,
                "features": XG_FEATURES if self.use_xg else BASE_FEATURES}

    def version_string(self) -> str:
        return f"{MODEL_VERSION}-xg" if self.use_xg else MODEL_VERSION


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


class SoftmaxRegression:
    """Multinomial logistic regression, full-batch GD, zeros init.

    Deterministic: fixed data order, no sampling, closed-form-free but
    repeatable iteration. Not claimed optimal — a reviewable baseline ML.
    """

    def __init__(self, l2: float = 1.0, learning_rate: float = 0.5,
                 iterations: int = 2000):
        self.l2 = l2
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.coef_: Optional[np.ndarray] = None  # (3, d+1), last col intercept
        self.mean_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None
        self.train_loss_: Optional[float] = None

    def _standardize(self, X: np.ndarray, fit: bool) -> np.ndarray:
        if fit:
            self.mean_ = X.mean(axis=0)
            self.scale_ = X.std(axis=0)
            self.scale_[self.scale_ == 0.0] = 1.0
        return (X - self.mean_) / self.scale_

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SoftmaxRegression":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        n, d = X.shape
        Xs = self._standardize(X, fit=True)
        Xb = np.hstack([Xs, np.ones((n, 1))])
        W = np.zeros((3, d + 1))
        Y = np.zeros((n, 3))
        Y[np.arange(n), y] = 1.0
        for _ in range(max(1, self.iterations)):
            probs = _softmax(Xb @ W.T)
            grad = (probs - Y).T @ Xb / n
            grad[:, :-1] += self.l2 * W[:, :-1] / n
            W -= self.learning_rate * grad
        self.coef_ = W
        final = _softmax(Xb @ W.T)
        self.train_loss_ = float(-np.mean(np.log(np.clip(
            final[np.arange(n), y], 1e-12, 1.0))))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise ValueError("model not fitted")
        X = np.asarray(X, dtype=float)
        Xs = (X - self.mean_) / self.scale_
        Xb = np.hstack([Xs, np.ones((X.shape[0], 1))])
        return _softmax(Xb @ self.coef_.T)


def build_feature_row(snapshot: Dict, use_xg: bool) -> Tuple[List[str], List[float], bool]:
    """Fixed-order vector + sufficiency flag. Missing xG (when required) or
    missing core blocks make the row unusable — returned, never imputed."""
    home, away = snapshot["home_team"], snapshot["away_team"]
    names = list(BASE_FEATURES)
    required = [home, away]
    if any(not block for block in required):
        return names, [], False
    elo_block = snapshot.get("elo", {})
    diff = elo_block.get("value", {}).get("diff") if isinstance(elo_block.get("value"), dict) else None
    if diff is None or not elo_block.get("available", False):
        return names, [], False
    form_h = home.get("form_last_5", {}).get("value", {})
    form_a = away.get("form_last_5", {}).get("value", {})
    gd_h = home.get("avg_goal_difference_5", {}).get("value")
    gd_a = away.get("avg_goal_difference_5", {}).get("value")
    rest_h = home.get("rest_days", {}).get("value")
    rest_a = away.get("rest_days", {}).get("value")
    if not home.get("form_last_5", {}).get("available") or \
            not away.get("form_last_5", {}).get("available"):
        return names, [], False
    if gd_h is None or gd_a is None:
        return names, [], False
    values = [float(diff),
              float(form_h.get("points_per_match", 0.0)) - float(form_a.get("points_per_match", 0.0)),
              float(gd_h) - float(gd_a),
              (float(rest_h) if rest_h is not None else 0.0)
              - (float(rest_a) if rest_a is not None else 0.0)]
    if use_xg:
        names = list(XG_FEATURES)
        xg_h = home.get("xg_last_5", {}).get("value", {})
        xg_a = away.get("xg_last_5", {}).get("value", {})
        if not home.get("xg_last_5", {}).get("available") or \
                not away.get("xg_last_5", {}).get("available"):
            return names, [], False
        try:
            values.append(float(xg_h.get("weighted_mean", 0.0))
                          - float(xg_a.get("weighted_mean", 0.0)))
        except (TypeError, ValueError):
            return names, [], False
    return names, values, True


def prediction_entropy(home: float, draw: float, away: float) -> float:
    """Shannon entropy of the 1X2 distribution (nats). Higher = less certain."""
    total = 0.0
    for prob in (home, draw, away):
        if prob > 0:
            total -= prob * math.log(prob)
    return total


class AdvancedModel:
    model_name = MODEL_NAME

    def __init__(self, config: Optional[AdvancedConfig] = None):
        self.config = config or AdvancedConfig()
        self.model_version = self.config.version_string()
        self.regression = SoftmaxRegression(
            l2=self.config.l2, learning_rate=self.config.learning_rate,
            iterations=self.config.iterations)
        self.train_meta: Dict = {}
        self._fitted = False

    def config_dict(self) -> Dict:
        return self.config.as_dict()

    def collect_training_rows(self, db: Session, matches: List[Match],
                              mode: TemporalMode) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        """Feature rows + labels for train matches. Rows lacking required
        features are DROPPED (counted) — never imputed. Each row uses only
        pre-cutoff history at that match's own kickoff."""
        from app.services.backtesting.runner import actual_outcome

        names: Optional[List[str]] = None
        vectors: List[List[float]] = []
        labels: List[int] = []
        dropped = 0
        for match in matches:
            cutoff = as_naive_utc(match.kickoff_at)
            try:
                snapshot = eng.build_feature_snapshot(
                    db, match.id, cutoff, mode,
                    eng.FeatureConfig(min_xg_matches=self.config.minimum_xg_matches))
            except ValueError:
                dropped += 1
                continue
            row_names, values, ok = build_feature_row(snapshot, self.config.use_xg)
            outcome = actual_outcome(match)
            if not ok or outcome is None:
                dropped += 1
                continue
            names = row_names
            vectors.append(values)
            labels.append({"home": 0, "draw": 1, "away": 2}[outcome])
        meta = {"rows": len(vectors), "dropped": dropped,
                "features": names or [], "use_xg": self.config.use_xg}
        if not vectors:
            return np.zeros((0, 0)), np.zeros((0,), dtype=int), [meta]
        return np.asarray(vectors), np.asarray(labels, dtype=int), [meta]

    def fit(self, db: Session, train_matches: List[Match],
            mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> Dict:
        """Fit on chronological training matches. Returns training metadata
        (persisted by callers to model_training_runs)."""
        X, y, metas = self.collect_training_rows(db, train_matches, mode)
        meta = metas[0]
        if X.shape[0] == 0:
            raise ValueError("no usable training rows (features unavailable)")
        self.regression.fit(X, y)
        self._fitted = True
        self.train_meta = dict(meta)
        self.train_meta.update({
            "train_loss": round(float(self.regression.train_loss_ or 0.0), 6),
            "coef": self.regression.coef_.tolist(),
            "scaler_mean": self.regression.mean_.tolist(),
            "scaler_scale": self.regression.scale_.tolist(),
        })
        return dict(self.train_meta)

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH) -> "FullPrediction":
        from app.services.predictions.outputs import FullPrediction

        availability = assess_availability(
            db, match_id, cutoff, mode,
            minimum_team_matches=5, minimum_xg_matches=self.config.minimum_xg_matches)
        if not self._fitted:
            return FullPrediction(
                model_name=self.model_name, model_version=self.model_version,
                status="insufficient_data",
                home_win_probability=1.0 / 3.0, draw_probability=1.0 / 3.0,
                away_win_probability=1.0 / 3.0, confidence=0.0, xg_used=False,
                feature_availability=availability.as_dict(),
                temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
                data_quality=["model not fitted; fit on a training window first",
                              "uniform probabilities are a placeholder, not an estimate"])
        try:
            snapshot = eng.build_feature_snapshot(
                db, match_id, cutoff, mode,
                eng.FeatureConfig(min_xg_matches=self.config.minimum_xg_matches))
        except ValueError as exc:
            return self._insufficient(availability, mode, cutoff, str(exc))
        names, values, ok = build_feature_row(snapshot, self.config.use_xg)
        if not ok:
            return self._insufficient(
                availability, mode, cutoff,
                "required features unavailable; see feature_availability")
        probs = self.regression.predict_proba(np.asarray([values]))[0]
        home_p, draw_p, away_p = (float(max(0.0, min(1.0, p))) for p in probs)
        total = home_p + draw_p + away_p
        home_p, draw_p, away_p = home_p / total, draw_p / total, away_p / total
        entropy = prediction_entropy(home_p, draw_p, away_p)
        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version, status="valid",
            home_win_probability=home_p, draw_probability=draw_p,
            away_win_probability=away_p,
            confidence=abs(home_p - away_p), xg_used=self.config.use_xg,
            confidence_basis="probability margin; entropy reported in data_quality",
            feature_availability=availability.as_dict(),
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            random_seed=0,
            data_quality=[f"features: {names}",
                          f"train_rows={self.train_meta.get('rows', '?')}",
                          f"entropy={entropy:.4f} nats (uncertainty, not correctness)",
                          "confidence_basis=probability margin; entropy reported separately"],
        )

    def _insufficient(self, availability, mode, cutoff, reason: str):
        from app.services.predictions.outputs import FullPrediction

        return FullPrediction(
            model_name=self.model_name, model_version=self.model_version,
            status="insufficient_data",
            home_win_probability=1.0 / 3.0, draw_probability=1.0 / 3.0,
            away_win_probability=1.0 / 3.0, confidence=0.0, xg_used=False,
            feature_availability=availability.as_dict() if hasattr(
                availability, "as_dict") else {},
            temporal_mode=mode.value, prediction_cutoff=str(as_naive_utc(cutoff)),
            data_quality=[reason, "uniform probabilities are a placeholder, not an estimate"])


class AdvancedGoalModel:
    """advanced_goal_v1: Poisson + half-life recency + xG blend + shrinkage.

    Differs from poisson_v1 (fixed decay, no shrinkage) and poisson_v1-xg
    (no shrinkage) by shrinking each lambda toward the league average when
    the responsible team history has 5-9 matches (w = n/10); below 5 matches
    the existing insufficient_data rule still applies. Compared
    chronologically — never assumed better.
    """
    model_name = GOAL_MODEL_NAME
    model_version = GOAL_MODEL_VERSION

    def __init__(self, half_life_days: float = 180.0, xg_weight: float = 0.5,
                 minimum_team_matches: int = 5, minimum_xg_matches: int = 3):
        from app.services.predictions.poisson import PoissonConfig as _PC

        self.half_life_days = half_life_days
        decay = math.log(2.0) / half_life_days if half_life_days > 0 else 0.01
        self.inner = PoissonModel(config=_PC(
            minimum_team_matches=minimum_team_matches,
            minimum_venue_matches=2,
            recency_decay=decay,
            xg_weight=xg_weight,
            minimum_xg_matches=minimum_xg_matches))
        self.inner.model_name = self.model_name
        self.inner.model_version = self.model_version

    def config_dict(self) -> Dict:
        inner = self.inner.config.as_dict()
        inner.update({"model": self.model_name, "half_life_days": self.half_life_days,
                      "shrinkage": "lambda blended toward league mean for 5-9 match histories"})
        return inner

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH):
        from app.services.features.repository import HistoricalFeatureRepository

        pred = self.inner.predict(db, match_id, cutoff, mode)
        if pred.status != "valid" or pred.expected_home_goals is None:
            pred.model_name = self.model_name
            pred.model_version = self.model_version
            return pred
        match = db.get(Match, match_id)
        repo = HistoricalFeatureRepository(db, cutoff, mode)
        league_hist = repo.finished_before(league_id=match.league_id)
        avg_home = sum(m.home_score or 0 for m in league_hist) / max(1, len(league_hist))
        avg_away = sum(m.away_score or 0 for m in league_hist) / max(1, len(league_hist))
        n_home = len(repo.team_matches_before(match.home_team_id))
        n_away = len(repo.team_matches_before(match.away_team_id))
        weight_home = min(1.0, n_home / 10.0)
        weight_away = min(1.0, n_away / 10.0)
        lam_home = weight_home * pred.expected_home_goals + (1.0 - weight_home) * avg_home
        lam_away = weight_away * pred.expected_away_goals + (1.0 - weight_away) * avg_away
        lam_home = min(6.0, max(0.05, lam_home))
        lam_away = min(6.0, max(0.05, lam_away))
        from app.services.predictions.math_utils import markets_from_grid, score_grid

        grid = score_grid(lam_home, lam_away, self.inner.config.max_grid_goals)
        markets = markets_from_grid(grid)
        pred.expected_home_goals = round(lam_home, 4)
        pred.expected_away_goals = round(lam_away, 4)
        pred.expected_total_goals = round(lam_home + lam_away, 4)
        pred.score_probabilities = {k: round(v, 6) for k, v in sorted(grid.items())}
        for key in ("home_win_probability", "draw_probability", "away_win_probability",
                    "over_1_5_probability", "under_1_5_probability",
                    "over_2_5_probability", "under_2_5_probability",
                    "over_3_5_probability", "under_3_5_probability",
                    "btts_yes_probability", "btts_no_probability"):
            setattr(pred, key, markets[key])
        pred.confidence = abs(markets["home_win_probability"] - markets["away_win_probability"])
        pred.model_name = self.model_name
        pred.model_version = self.model_version
        pred.data_quality = list(pred.data_quality or []) + [
            f"shrinkage weights home={weight_home:.2f} away={weight_away:.2f}",
            f"half_life_days={self.half_life_days}"]
        return pred


def fit_temperature(probs_list, actual_list) -> float:
    """Single-temperature scaling on 1X2 logits (calibration_v1).

    Golden-section search on NLL over T in [0.05, 10]. Deterministic.
    Fit ONLY on training/validation outcomes — never test outcomes.
    """
    pairs = [(np.asarray(p, dtype=float), int(a))
             for p, a in zip(probs_list, actual_list)]
    pairs = [(p / p.sum(), a) for p, a in pairs if p.sum() > 0]
    if not pairs:
        return 1.0

    def nll(temperature: float) -> float:
        total = 0.0
        for probs, actual in pairs:
            logits = np.log(np.clip(probs, 1e-12, 1.0)) / max(temperature, 1e-6)
            shifted = logits - logits.max()
            exp = np.exp(shifted)
            scaled = exp / exp.sum()
            total += -math.log(max(scaled[actual], 1e-12))
        return total / len(pairs)

    lo, hi = 0.05, 10.0
    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    for _ in range(60):
        m1 = hi - inv_phi * (hi - lo)
        m2 = lo + inv_phi * (hi - lo)
        if nll(m1) < nll(m2):
            hi = m2
        else:
            lo = m1
    return round((lo + hi) / 2.0, 4)


def apply_temperature(probs: List[float], temperature: float) -> List[float]:
    arr = np.asarray(probs, dtype=float)
    logits = np.log(np.clip(arr / arr.sum(), 1e-12, 1.0)) / max(temperature, 1e-6)
    shifted = logits - logits.max()
    exp = np.exp(shifted)
    scaled = exp / exp.sum()
    return [float(v) for v in scaled]


class CalibratedModel:
    """Wraps a fitted base model with a train-fitted temperature.

    model_version appends '-cal' (new version for changed parameters).
    """

    def __init__(self, base_model, temperature: float = 1.0,
                 train_window: Optional[str] = None):
        self.base_model = base_model
        self.temperature = temperature
        self.train_window = train_window or ""
        self.model_name = getattr(base_model, "model_name", "?")
        self.model_version = f"{getattr(base_model, 'model_version', '?')}-cal"

    @property
    def model_names(self):
        return [self.model_name]

    def config_dict(self) -> Dict:
        base_config = None
        config = getattr(self.base_model, "config", None)
        if config is not None and hasattr(config, "as_dict"):
            try:
                base_config = config.as_dict()
            except Exception:
                base_config = None
        if base_config is None and hasattr(self.base_model, "config_dict"):
            try:
                base_config = self.base_model.config_dict()
            except Exception:
                base_config = None
        return {"calibration": CALIBRATION_VERSION, "temperature": self.temperature,
                "train_window": self.train_window, "base_config": base_config}

    def predict(self, db: Session, match_id: int, cutoff: datetime,
                mode: TemporalMode = TemporalMode.STRICT_PREMATCH):
        pred = self.base_model.predict(db, match_id, cutoff, mode)
        if pred.status != "valid":
            pred.model_name = self.model_name
            return pred
        scaled = apply_temperature(
            [pred.home_win_probability, pred.draw_probability,
             pred.away_win_probability], self.temperature)
        pred.home_win_probability, pred.draw_probability, pred.away_win_probability = scaled
        pred.model_name = self.model_name
        pred.model_version = self.model_version
        pred.data_quality = list(pred.data_quality or []) + [
            f"temperature={self.temperature} fitted on {self.train_window or 'train window'} only"]
        return pred
