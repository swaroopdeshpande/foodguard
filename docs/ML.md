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
- **Features**: 15 columns in `app/ml/food_risk/features.py::FEATURE_COLUMNS`
  — days_to_expiry, **pct_shelf_life_remaining**, perishability_level,
  current_temperature, temperature_deviation, cumulative_temperature_exposure,
  humidity, storage_deviation_duration, supplier_defect_rate,
  supplier_reliability, batch_age, previous_rejection_rate, consumption_rate,
  consumption_change, historical_incidents.
- **Why pct_shelf_life_remaining exists** (found via manual-entry testing,
  not caught by automated tests originally): raw `days_to_expiry` alone
  can't generalize across categories with wildly different shelf lives.
  A fresh rice batch (300 of 540 days left) and a fresh chicken batch (4 of
  4 days left) both look "safe," but the *first* model version was trained
  on `days_to_expiry` sampled from one uniform `-2..30` range regardless of
  category — so a real rice batch's `days_to_expiry≈300` was wildly outside
  anything the model had seen, an unpredictable extrapolation. Fixed by:
  (1) adding `pct_shelf_life_remaining = days_to_expiry / expected_shelf_life_days`
  as a category-normalized feature, (2) resampling training data with
  **per-category-realistic shelf-life ranges** (`train.py::_SHELF_LIFE_RANGE_BY_PERISHABILITY`,
  2-5 days for perishability 5 down to 180-540 days for perishability 1)
  instead of one uniform range for every row, (3) rewriting `synthetic_label`
  to drive expiry-urgency primarily off `pct_shelf_life_remaining` (full
  weight at ≤0% remaining, zero weight at ≥25% remaining) with raw
  `days_to_expiry≤0` kept only as a small secondary "physically past date"
  term. Verified against the live DB post-fix: all 35 Rice/Canned-Goods
  batches in the demo dataset now correctly score LOW (previously several
  were miscategorized).
- **Follow-up fix**: a flat 25%-shelf-life-remaining cutoff for every
  category meant chicken with 1 of 4 days left (exactly 25%) scored as
  safe as fresh (0% risk) — technically consistent with the formula, but
  wrong in practice for a highly perishable item. `_urgency_cutoff()` now
  scales the cutoff itself by `perishability_level`: 50% remaining for
  the most perishable items (chicken/fish) down to 8% for shelf-stable
  ones (rice/canned) — linear interpolation across the 1-5 scale.
  Re-verified live: same 1-of-4-days chicken batch now scores HIGH/88.7%
  → `DO_NOT_SERVE`, fresh chicken stays LOW/0%, rice at a comparable
  ~25% point stays LOW.
- 6 unit tests (`tests/unit/test_food_risk_features.py`) lock in both
  fixes permanently. Note: tests compare `deterministic_risk_score()`
  (the formula without its Gaussian noise term) rather than the final
  noisy `synthetic_label()` output where equality matters — a real flake
  was found while tuning the cutoff weight, where two rows with an
  intentionally-identical underlying score landed on opposite sides of
  the label threshold purely because each call draws its own independent
  noise sample.
- **Training labels**: since no real incident-labeled dataset exists, labels
  come from `features.synthetic_label()` — a documented weighted-rule formula
  (expiry proximity + perishability + cumulative temp exposure + storage
  deviation + supplier reliability + rejection rate + consumption drop +
  historical incidents, plus Gaussian noise). This is exactly the "rule
  weights get learned instead of hand-tuned" idea from the spec, but the
  ground truth is synthetic-by-construction.
- **Result on last training run** (20,000 synthetic rows): precision 0.95,
  recall 0.95, F1 0.95, ROC-AUC 0.998. **This is expected to be near-perfect**
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
