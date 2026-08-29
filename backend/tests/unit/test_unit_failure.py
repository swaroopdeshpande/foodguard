import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.anomaly.unit_failure import detect_unit_incident  # noqa: E402


def _rising_series(start: float, end: float, n: int) -> pd.Series:
    return pd.Series([start + (end - start) * i / (n - 1) for i in range(n)])


def test_detects_correlated_rising_risk_across_batches():
    series = {
        "batch_a": _rising_series(0.1, 0.7, 10),
        "batch_b": _rising_series(0.15, 0.75, 10),
        "batch_c": _rising_series(0.05, 0.65, 10),
    }
    result = detect_unit_incident(series)
    assert result is not None
    assert len(result.affected_batch_ids) == 3
    assert result.correlation_score > 0.7
    assert result.severity == "HIGH"


def test_does_not_flag_independent_flat_batches():
    series = {
        "batch_a": pd.Series([0.1] * 10),
        "batch_b": pd.Series([0.2, 0.1, 0.25, 0.15, 0.1, 0.2, 0.1, 0.15, 0.1, 0.12]),
        "batch_c": pd.Series([0.05] * 10),
    }
    result = detect_unit_incident(series)
    assert result is None


def test_requires_minimum_co_occurring_batches():
    series = {"batch_a": _rising_series(0.1, 0.9, 10), "batch_b": _rising_series(0.1, 0.9, 10)}
    result = detect_unit_incident(series, min_co_occurring=3)
    assert result is None
