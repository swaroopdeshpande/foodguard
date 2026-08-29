"""
Trains ML Model #1: food-risk classifier (XGBoost, RandomForest fallback).

DATA_SOURCE = SYNTHETIC. Generates a large feature dataset with the same
schema as live inference (see features.FEATURE_COLUMNS), using controlled
distributions that encode the domain relationships documented in ML.md,
then labels each row via features.synthetic_label(). This is how the
model learns *feature importance weights* from data instead of the
original hand-tuned rule weights being hardcoded -- but the ground truth
itself is synthetic and must never be presented as real-world validation.

Run:
    backend/venv/bin/python -m app.ml.food_risk.train --n 20000
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

sys.path.append(str(Path(__file__).resolve().parents[3]))

from app.ml.food_risk.features import FEATURE_COLUMNS, synthetic_label  # noqa: E402

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:  # ImportError, or xgboost.core.XGBoostError if libomp isn't installed
    HAS_XGB = False

RNG = np.random.default_rng(42)
MODEL_DIR = Path(__file__).resolve().parents[4] / "models" / "food_risk"


# perishability_level -> realistic shelf-life range (days), matching the
# category defs in scripts/generate_demo_data.py (5=fish/chicken ~2-5 days,
# 1=rice/canned ~200-540 days). Sampling shelf_life PER ROW like this (instead
# of one uniform days_to_expiry range for every row regardless of category)
# is what makes pct_shelf_life_remaining a meaningful, learnable feature --
# see the note on synthetic_label and ML.md for why raw days_to_expiry alone
# can't generalize across a 2-day vs 540-day shelf life.
_SHELF_LIFE_RANGE_BY_PERISHABILITY = {
    5: (2, 5),
    4: (5, 10),
    3: (5, 21),
    2: (20, 60),
    1: (180, 540),
}


def _sample_shelf_life_days(perishability_levels: np.ndarray) -> np.ndarray:
    out = np.empty(len(perishability_levels), dtype=float)
    for level, (lo, hi) in _SHELF_LIFE_RANGE_BY_PERISHABILITY.items():
        mask = perishability_levels == level
        out[mask] = RNG.uniform(lo, hi, mask.sum())
    return out


def generate_training_frame(n: int) -> pd.DataFrame:
    perishability = RNG.integers(1, 6, n)
    shelf_life_days = _sample_shelf_life_days(perishability)
    # -0.15 to 1.3: covers "already expired" through "fresh with margin", same
    # distribution shape regardless of the row's absolute shelf_life_days
    pct_shelf_life_remaining = RNG.uniform(-0.15, 1.3, n)
    days_to_expiry = np.round(pct_shelf_life_remaining * shelf_life_days).astype(int)

    df = pd.DataFrame({
        "days_to_expiry": days_to_expiry,
        "pct_shelf_life_remaining": pct_shelf_life_remaining,
        "perishability_level": perishability,
        "storage_deviation_duration": np.clip(RNG.exponential(1.5, n), 0, 24).round(1),
        "supplier_reliability": np.clip(RNG.normal(0.8, 0.15, n), 0, 1),
        "previous_rejection_rate": np.clip(RNG.exponential(0.03, n), 0, 0.5),
        "consumption_change": np.clip(RNG.normal(0, 0.25, n), -0.9, 2),
        "historical_incidents": RNG.poisson(0.6, n),
    })
    df["supplier_defect_rate"] = np.clip(1 - df.supplier_reliability + RNG.normal(0, 0.03, n), 0, 0.5)
    df["cumulative_temperature_exposure"] = np.clip(
        df.storage_deviation_duration * RNG.uniform(0.5, 2.5, n), 0, 40
    )
    df["current_temperature"] = RNG.normal(4, 2, n)
    df["temperature_deviation"] = np.clip(df.cumulative_temperature_exposure / (df.storage_deviation_duration + 1), 0, 6)
    df["humidity"] = RNG.normal(50, 8, n)
    df["batch_age"] = np.clip((1 - pct_shelf_life_remaining) * shelf_life_days, 0, None).round().astype(int)
    df["consumption_rate"] = np.clip(RNG.normal(15, 5, n), 0, None)

    df = df[FEATURE_COLUMNS]
    df["label"] = df.apply(synthetic_label, axis=1)
    return df


def train(n: int, model_name: str = "food_risk"):
    print(f"DATA_SOURCE = SYNTHETIC | generating {n} training rows...")
    df = generate_training_frame(n)
    X, y = df[FEATURE_COLUMNS], df["label"]
    print(f"Positive class rate: {y.mean():.3f}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    if HAS_XGB:
        model = XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.08,
            subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
            random_state=42,
        )
        algo_used = "XGBClassifier"
    else:
        model = RandomForestClassifier(n_estimators=300, max_depth=8, random_state=42)
        algo_used = "RandomForestClassifier (xgboost unavailable, fallback)"

    print(f"Training {algo_used}...")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "algorithm": algo_used,
        "precision": round(precision_score(y_test, y_pred), 4),
        "recall": round(recall_score(y_test, y_pred), 4),
        "f1": round(f1_score(y_test, y_pred), 4),
        "roc_auc": round(roc_auc_score(y_test, y_proba), 4),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "data_source": "SYNTHETIC",
    }
    print(json.dumps(metrics, indent=2))
    print(classification_report(y_test, y_pred))

    if hasattr(model, "feature_importances_"):
        importances = dict(zip(FEATURE_COLUMNS, [round(float(v), 4) for v in model.feature_importances_]))
        print("Feature importances:", json.dumps(importances, indent=2))
        metrics["feature_importances"] = importances

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")
    model_path = MODEL_DIR / f"{model_name}_{version}.joblib"

    import joblib
    joblib.dump(model, model_path)
    (MODEL_DIR / "latest.json").write_text(json.dumps({
        "model_path": str(model_path), "version": version, "metrics": metrics,
        "feature_columns": FEATURE_COLUMNS, "trained_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    print(f"Saved model -> {model_path}")
    return model, metrics, version


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20000)
    args = parser.parse_args()
    train(args.n)
