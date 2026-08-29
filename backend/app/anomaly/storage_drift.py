"""
ML Model #2: storage time-series anomaly detection.

Pipeline per storage unit:
  1. Rolling baseline (mean/std/median/IQR) -> per-unit adaptive "normal" range,
     not a fixed global threshold.
  2. Local statistical forecast (Holt-Winters exponential smoothing via
     statsmodels -- Prophet skipped: unreliable cmdstan build on student
     laptops, statsmodels is pure-python and zero-hassle).
  3. residual = actual - predicted.
  4. CUSUM on the residual stream to detect persistent (not one-off) shifts.
  5. Linear trend fit on the recent window -> estimated_days_to_threshold.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import SimpleExpSmoothing


@dataclass
class DriftResult:
    anomaly_type: str | None
    severity: str
    current_value: float
    expected_value: float
    residual: float
    trend_per_day: float | None
    estimated_days_to_threshold: float | None
    details: dict


def rolling_baseline(series: pd.Series, window: int = 24 * 7) -> dict:
    recent = series.iloc[-window:] if len(series) > window else series
    q1, q3 = recent.quantile(0.25), recent.quantile(0.75)
    return {
        "rolling_mean": float(recent.mean()),
        "rolling_std": float(recent.std(ddof=0) or 1e-6),
        "median": float(recent.median()),
        "iqr": float(q3 - q1),
    }


def forecast_next(series: pd.Series) -> float:
    """Simple exponential smoothing one-step-ahead forecast. Falls back to
    rolling mean if statsmodels can't fit (e.g. too few points / degenerate series)."""
    try:
        model = SimpleExpSmoothing(series.values, initialization_method="estimated").fit()
        return float(model.forecast(1)[0])
    except Exception:
        return float(series.iloc[-12:].mean())


def cusum(residuals: np.ndarray, k: float | None = None, h: float = 5.0) -> tuple[bool, float]:
    """One-sided CUSUM for detecting a persistent upward shift.
    k = allowance (slack), h = decision threshold, both in units of residual std."""
    std = residuals.std(ddof=0) or 1e-6
    k = k if k is not None else 0.5 * std
    s_pos = 0.0
    max_s = 0.0
    for r in residuals:
        s_pos = max(0.0, s_pos + r - k)
        max_s = max(max_s, s_pos)
    return bool(max_s > h * std), float(max_s / std)


def linear_trend_per_day(series: pd.Series, freq_per_day: int = 24) -> float:
    """Slope of a linear fit over the recent window, expressed as units/day."""
    recent = series.iloc[-freq_per_day * 8:]  # last 8 days
    if len(recent) < freq_per_day:
        return 0.0
    x = np.arange(len(recent))
    slope_per_point = np.polyfit(x, recent.values, 1)[0]
    return float(slope_per_point * freq_per_day)


def analyze_unit_series(
    readings: pd.DataFrame, target_temp: float, threshold_max: float, threshold_min: float,
) -> DriftResult:
    """readings: DataFrame with columns ts, temperature_c, sorted ascending."""
    series = readings.set_index("ts")["temperature_c"].astype(float)
    if len(series) < 24:
        return DriftResult(None, "LOW", float(series.iloc[-1]) if len(series) else target_temp,
                            target_temp, 0.0, None, None, {"reason": "insufficient_history"})

    baseline = rolling_baseline(series)
    predicted = forecast_next(series.iloc[:-1])
    current = float(series.iloc[-1])
    residual = current - predicted

    window_residuals = (series.iloc[-24 * 7:] - baseline["rolling_mean"]).values
    shifted, cusum_strength = cusum(window_residuals)

    trend = linear_trend_per_day(series)
    estimated_days = None
    if trend > 0.01 and current < threshold_max:
        estimated_days = round((threshold_max - current) / trend, 1)
    elif trend < -0.01 and current > threshold_min:
        estimated_days = round((current - threshold_min) / abs(trend), 1)

    anomaly_type = None
    severity = "LOW"
    if current > threshold_max or current < threshold_min:
        anomaly_type = "THRESHOLD_BREACH"
        severity = "HIGH"
    elif shifted:
        anomaly_type = "CUSUM_SHIFT"
        severity = "MEDIUM" if cusum_strength < 6 else "HIGH"
    elif estimated_days is not None and estimated_days <= 7:
        anomaly_type = "TEMPERATURE_DRIFT"
        severity = "HIGH" if estimated_days <= 3 else "MEDIUM"
    elif abs(residual) > 3 * baseline["rolling_std"]:
        anomaly_type = "SPIKE"
        severity = "MEDIUM"

    return DriftResult(
        anomaly_type=anomaly_type, severity=severity, current_value=round(current, 2),
        expected_value=round(predicted, 2), residual=round(residual, 2),
        trend_per_day=round(trend, 3), estimated_days_to_threshold=estimated_days,
        details={"baseline": baseline, "cusum_strength": round(cusum_strength, 2)},
    )
