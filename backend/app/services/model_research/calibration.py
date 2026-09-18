"""Calibration as separate versions (Phase 12).

Raw and temperature-scaled variants are evaluated side by side; the
temperature is fit on validation outcomes only. Reports log loss, Brier,
ECE and reliability — calibration never touches the test set.
"""
from __future__ import annotations

from typing import Dict, List

from app.services.backtesting import metrics as met
from app.services.model_research import training as training_svc


def evaluate_calibration(probs_val, actual_val, probs_test, actual_test,
                         n_bins: int = 10) -> Dict:
    temperature = training_svc.fit_temperature(probs_val, actual_val)
    calibrated = training_svc.apply_temperature(probs_test, temperature)
    home_val = [p[0] for p in probs_val]
    home_test = [p[0] for p in probs_test]
    home_test_cal = [p[0] for p in calibrated]
    actual_home_test = [1 if a == 0 else 0 for a in actual_test]
    return {
        "temperature": temperature,
        "fitted_on": "validation",
        "raw": {"log_loss": round(met.multiclass_log_loss(probs_test, actual_test), 4),
                "brier": round(met.multiclass_brier(probs_test, actual_test), 4),
                "ece_home": round(met.expected_calibration_error(
                    home_test, actual_home_test, n_bins=n_bins), 4)},
        "calibrated": {
            "log_loss": round(met.multiclass_log_loss(calibrated, actual_test), 4),
            "brier": round(met.multiclass_brier(calibrated, actual_test), 4),
            "ece_home": round(met.expected_calibration_error(
                home_test_cal, actual_home_test, n_bins=n_bins), 4)},
        "version_suffix": "-cal",
    }
