"""
ML Model #3: supplier behavioural anomaly detection.

Isolation Forest fit PER SUPPLIER on that supplier's own delivery history
(not a single global model) -- a delivery is scored against the supplier's
own baseline, so "batch size = 58kg" only looks anomalous for a supplier
whose normal batch size is ~100kg, not against the whole population.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "batch_size_kg", "delivery_delay_days", "defect_rate",
    "rejected_quantity_kg", "complaint_count", "price_per_kg", "remaining_shelf_life_days",
]

MIN_HISTORY = 6  # need at least this many past deliveries to fit a meaningful baseline


@dataclass
class SupplierAnomalyResult:
    is_anomaly: bool
    anomaly_score: float  # higher = more anomalous, normalized 0-1
    severity: str
    deviating_features: dict


def score_latest_delivery(history: pd.DataFrame) -> SupplierAnomalyResult | None:
    """history: all deliveries for one supplier, ordered by delivered_at ascending.
    Scores the LAST row against an IsolationForest fit on the rest."""
    if len(history) < MIN_HISTORY + 1:
        return None

    train = history.iloc[:-1][FEATURES]
    latest = history.iloc[[-1]][FEATURES]

    scaler = StandardScaler()
    X_train = scaler.fit_transform(train)
    X_latest = scaler.transform(latest)

    model = IsolationForest(n_estimators=150, contamination="auto", random_state=42)
    model.fit(X_train)

    raw_score = -model.score_samples(X_latest)[0]  # higher = more anomalous
    # normalize against training distribution's own score range for interpretability
    train_scores = -model.score_samples(X_train)
    lo, hi = train_scores.min(), train_scores.max()
    normalized = float(np.clip((raw_score - lo) / (hi - lo + 1e-9), 0, 1))

    is_anomaly = model.predict(X_latest)[0] == -1

    deviations = {}
    for col in FEATURES:
        mu, sigma = train[col].mean(), train[col].std(ddof=0) or 1e-6
        z = (latest[col].iloc[0] - mu) / sigma
        if abs(z) > 1.5:
            deviations[col] = {
                "value": round(float(latest[col].iloc[0]), 3),
                "supplier_baseline_mean": round(float(mu), 3),
                "z_score": round(float(z), 2),
            }

    severity = "LOW"
    if normalized > 0.75:
        severity = "HIGH"
    elif normalized > 0.5:
        severity = "MEDIUM"

    return SupplierAnomalyResult(
        is_anomaly=bool(is_anomaly), anomaly_score=round(normalized, 4),
        severity=severity, deviating_features=deviations,
    )
