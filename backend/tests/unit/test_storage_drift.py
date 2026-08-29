import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.anomaly.storage_drift import analyze_unit_series, cusum  # noqa: E402


def test_cusum_flags_persistent_upward_shift():
    rng = np.random.default_rng(1)
    stable = rng.normal(0, 0.2, 100)
    shifted = rng.normal(1.5, 0.2, 40)
    residuals = np.concatenate([stable, shifted])
    flagged, strength = cusum(residuals)
    assert flagged is True
    assert strength > 4


def test_cusum_does_not_flag_pure_noise():
    rng = np.random.default_rng(2)
    residuals = rng.normal(0, 0.3, 200)
    flagged, _ = cusum(residuals)
    assert flagged is False


def test_analyze_unit_series_flags_drifting_fridge():
    ts = pd.date_range("2026-01-01", periods=24 * 20, freq="h")
    temps = [4.0 + max(0, i - 24 * 12) * (0.38 / 24) for i in range(len(ts))]
    df = pd.DataFrame({"ts": ts, "temperature_c": temps})
    result = analyze_unit_series(df, target_temp=4.0, threshold_max=6.5, threshold_min=1.5)
    assert result.anomaly_type is not None
    assert result.severity in ("MEDIUM", "HIGH")


def test_analyze_unit_series_normal_unit_is_clean():
    rng = np.random.default_rng(3)
    ts = pd.date_range("2026-01-01", periods=24 * 20, freq="h")
    temps = 4.0 + rng.normal(0, 0.2, len(ts))
    df = pd.DataFrame({"ts": ts, "temperature_c": temps})
    result = analyze_unit_series(df, target_temp=4.0, threshold_max=6.5, threshold_min=1.5)
    assert result.anomaly_type is None
    assert result.severity == "LOW"
