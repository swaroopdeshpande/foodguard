"""
Correlated multi-item failure detection.

If several independently-scored food batches in the SAME storage unit
spike in risk within the same time window, that's evidence of a unit-level
root cause (compressor failing, door left open) rather than N unrelated
item-level problems. Reduces alert fatigue: 1 unit incident instead of
N separate per-item alerts (spec section 10).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class UnitIncidentResult:
    affected_batch_ids: list[str]
    correlation_score: float
    severity: str


def detect_unit_incident(
    batch_risk_series: dict[str, pd.Series], min_co_occurring: int = 3, window: int = 24,
) -> UnitIncidentResult | None:
    """batch_risk_series: {batch_id: chronological risk-probability series} for all
    batches currently stored in one unit. Flags a unit incident if >= min_co_occurring
    of them show a simultaneous upward move in the same recent window."""
    if len(batch_risk_series) < min_co_occurring:
        return None

    deltas = {}
    for bid, series in batch_risk_series.items():
        recent = series.iloc[-window:] if len(series) > window else series
        if len(recent) < 2:
            continue
        deltas[bid] = float(recent.iloc[-1] - recent.iloc[0])

    rising = {bid: d for bid, d in deltas.items() if d > 0.15}  # meaningfully rising
    if len(rising) < min_co_occurring:
        return None

    # pairwise correlation of the rising batches' trajectories as co-movement evidence
    aligned = pd.DataFrame({bid: batch_risk_series[bid].iloc[-window:].reset_index(drop=True) for bid in rising})
    aligned = aligned.dropna(axis=1, how="any")
    if aligned.shape[1] < min_co_occurring:
        return None

    corr_matrix = aligned.corr(method="pearson").values
    avg_corr = float(np.nanmean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)]))

    severity = "HIGH" if avg_corr > 0.7 and len(rising) >= min_co_occurring else "MEDIUM"

    return UnitIncidentResult(
        affected_batch_ids=list(rising.keys()), correlation_score=round(avg_corr, 3), severity=severity,
    )
