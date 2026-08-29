# FoodGuard — ML Methodology

## DATA_SOURCE = SYNTHETIC

No real hotel/restaurant/supplier data is used anywhere in this project. All
training and demo data comes from `scripts/generate_demo_data.py`, a
domain-informed generator — never claim any metric here as real-world
validation. This is disclosed on every training run and in every metrics
artifact (`models/food_risk/latest.json`).

## Model #1 — Food Risk Classifier

- **Algorithm**: XGBoost (`XGBClassifier`), RandomForest fallback if xgboost's
  native lib fails to load (common on macOS without `libomp` — the code
  catches this and falls back automatically, see `train.py`).
- **Features**: 14 columns in `app/ml/food_risk/features.py::FEATURE_COLUMNS`
  — days_to_expiry, perishability_level, current_temperature,
  temperature_deviation, cumulative_temperature_exposure, humidity,
  storage_deviation_duration, supplier_defect_rate, supplier_reliability,
  batch_age, previous_rejection_rate, consumption_rate, consumption_change,
  historical_incidents.
- **Training labels**: since no real incident-labeled dataset exists, labels
  come from `features.synthetic_label()` — a documented weighted-rule formula
  (expiry proximity + perishability + cumulative temp exposure + storage
  deviation + supplier reliability + rejection rate + consumption drop +
  historical incidents, plus Gaussian noise). This is exactly the "rule
  weights get learned instead of hand-tuned" idea from the spec, but the
  ground truth is synthetic-by-construction.
- **Result on last training run** (20,000 synthetic rows): precision 0.96,
  recall 0.95, F1 0.95, ROC-AUC 0.999. **This is expected to be near-perfect**
  because the label is a deterministic function of the features it's trained
  on — it demonstrates the model correctly *recovers* the encoded relationship,
  not real-world food-safety accuracy. Say this explicitly in viva.
- **Explainability**: feature importances stored per-prediction as
  `top_factors` (top-5) on every `risk_predictions` row — no SHAP dependency
  needed for the demo, but SHAP is a drop-in upgrade path (`shap.TreeExplainer`
  works directly on the saved XGBoost model).

## Model #2 — Storage Drift / Anomaly Detection

- **Not Prophet.** Prophet's cmdstan build is unreliable on student laptops
  (long native compile, frequent install failures) — used **statsmodels'
  SimpleExpSmoothing** instead, which is pure-Python, installs cleanly, and is
  sufficient for one-step-ahead residual computation at this scale.
- **Pipeline**: rolling baseline (mean/std/median/IQR, 7-day window) → 1-step
  forecast → residual = actual − predicted → one-sided CUSUM on the residual
  stream (catches *persistent* shifts, not single noisy readings) → linear
  trend fit over the last 8 days → `estimated_days_to_threshold`.
- **Verified**: on the `fridge_drift` synthetic scenario (FRIDGE_03, +0.38°C/day
  over 8 days), correctly flags `CUSUM_SHIFT`/`TEMPERATURE_DRIFT` at HIGH
  severity while FRIDGE_01 (flat, noise-only) stays clean. See
  `backend/tests/unit/test_storage_drift.py`.

## Model #3 — Supplier Behavioural Anomaly

- **Algorithm**: `IsolationForest`, fit **per supplier** on that supplier's
  own delivery history (not one global model across all suppliers) — this is
  the point: a delivery is judged against *that supplier's own baseline*.
  Requires ≥7 historical deliveries before scoring (`MIN_HISTORY`).
- **Features**: batch_size_kg, delivery_delay_days, defect_rate,
  rejected_quantity_kg, complaint_count, price_per_kg, remaining_shelf_life_days.
- **Verified**: on the `supplier_anomaly` scenario, the injected supplier
  (batch size ↓, delay ↑, defect rate ↑, shelf life ↓) is correctly flagged
  HIGH with the exact deviating features reported by z-score.
- **Known noise source**: a supplier's category assignment is randomized per
  delivery in the generator (60% specialization, 40% random category), which
  occasionally produces a spurious `remaining_shelf_life_days` outlier for an
  otherwise-normal supplier (e.g. a dairy delivery randomly tagged as
  Canned Goods). Documented rather than "fixed" — it demonstrates the model
  reacting to genuine input variance, which real data will also have.

## Consumption Anomaly

Rolling z-score / percent-change on daily consumption totals per food item.
Deliberately simple and transparent — this signal is a cross-reference input,
**never** a standalone "unsafe" verdict (enforced in the fusion engine: see
`test_consumption_anomaly_never_auto_declares_unsafe`).

## Label / Fraud Consistency

Pure rule-based, not ML — a fraud/audit finding must be explainable and
defensible, not a black-box score. Three checks: mfg-before-expiry,
shelf-life-vs-category-norm consistency, and duplicate batch-code reuse
across a ≥20-day gap. Verified against the `label_fraud` scenario (a batch
code planted on day 2, reused ~100 days later with an inflated shelf life) —
both `POSSIBLE_BATCH_REUSE` and `INCONSISTENT_SHELF_LIFE` fire correctly.

## Correlated Unit-Failure Detection

Requires a **history** of risk scores per batch (multiple pipeline runs over
time) to compute co-movement/correlation — a single pipeline pass only has
one risk snapshot per batch. `run_unit_failure_detection` (in `pipeline.py`)
reads the accumulated `risk_predictions` rows per batch per storage unit and
calls `detect_unit_incident` (Pearson correlation of co-rising risk
trajectories, ≥3 batches required).

**Honest caveat**: two pipeline runs against *static* historical data produce
*identical* risk scores (nothing changed in between), so `delta > 0.15`
never trips and no incident fires — verified this directly (`run 1` and
`run 2` both returned `unit_failure_incidents: 0` against unchanged data).
This is correct behavior, not a bug: the detector needs genuine risk
*progression* over time, which only happens as real (or simulated) time
passes and conditions actually worsen — e.g. across successive
`/api/simulation/trigger` calls as a scenario's storage drift continues.

Verification split accordingly:
- **Algorithm-level** (`tests/unit/test_unit_failure.py`): 3 tests, pure
  synthetic risk series, proves correlation logic is correct in isolation.
- **Wiring-level** (`tests/e2e/test_unit_failure_pipeline.py`): seeds
  progressing `risk_predictions` rows directly for 3 batches sharing a
  storage unit against the real Postgres DB, proves `run_unit_failure_detection`
  correctly creates a `UnitIncident` row + a `MAINTENANCE`-routed `Incident`,
  and that it's actually persisted (not just returned in-memory). Cleans up
  after itself so repeated runs don't pollute the demo DB.

## Fusion Engine

Combines every signal above into one routed `Incident` — see
`app/services/fusion.py` and `docs/ARCHITECTURE.md`. Priority order:
label/fraud > food-risk HIGH > unit-incident > storage anomaly > supplier
anomaly > food-risk MEDIUM > consumption anomaly > SAFE. Every dimension is
kept in `dimensions_snapshot`, not collapsed into a single number.

## Known limitations (say these upfront in the report, don't wait to be asked)

1. Synthetic labels mean classification metrics measure label-recoverability,
   not real-world food-safety accuracy — stated wherever metrics are shown.
2. The data generator never marks old batches CONSUMED/DISCARDED, so a
   120-day run accumulates an unrealistic backlog of long-expired
   "IN_STOCK" batches, inflating DO_NOT_SERVE counts. Acceptable for a
   scenario-focused demo; would need batch-lifecycle transitions for a
   longer-running deployment.
3. Correlated unit-failure detection is wired end-to-end but only fires
   when risk scores actually progress between pipeline runs (see above) —
   demoing it live needs a scenario run across genuinely advancing time
   (repeated simulation triggers), not two instantaneous runs.
4. No real supplier/hotel data has been used or is claimed anywhere.
