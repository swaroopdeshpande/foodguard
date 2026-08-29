"""
Consumption/wastage pattern anomaly detection.

Deliberately simple, transparent stats (rolling mean/std/z-score) --
this signal is meant to catch "staff are quietly avoiding an item" as an
early human sensor, and cross-reference it against the ML food-risk score.
It must NOT unilaterally declare food unsafe (see spec section 11).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ConsumptionAnomalyResult:
    z_score: float
    pct_change: float
    severity: str
    recommendation: str


def detect_consumption_anomaly(
    daily_quantities: pd.Series, current_food_risk: float | None = None,
) -> ConsumptionAnomalyResult | None:
    """daily_quantities: chronological daily consumption totals for one food item."""
    if len(daily_quantities) < 6:
        return None

    baseline = daily_quantities.iloc[:-1]
    latest = float(daily_quantities.iloc[-1])
    mu, sigma = baseline.mean(), (baseline.std(ddof=0) or 1e-6)
    z = (latest - mu) / sigma
    pct_change = (latest - mu) / mu if mu else 0.0

    if abs(z) < 1.5:
        return None  # not anomalous enough to report

    severity = "MEDIUM" if abs(z) < 3 else "HIGH"

    recommendation = "INVESTIGATE"
    if current_food_risk is not None and current_food_risk < 0.3 and z < -1.5:
        # spec example: food risk LOW but consumption dropped hard -> flag for investigation,
        # do not auto-declare unsafe
        recommendation = "INVESTIGATE"

    return ConsumptionAnomalyResult(
        z_score=round(float(z), 2), pct_change=round(float(pct_change), 3),
        severity=severity, recommendation=recommendation,
    )
