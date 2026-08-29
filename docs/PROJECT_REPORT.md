# FoodGuard
## ML-Based Food Safety Risk Prediction and Multi-Source Anomaly Detection System

---

## Abstract

FoodGuard is a locally-run software system that predicts food-safety risk
and detects operational anomalies for restaurants and hotels, using only
open-source ML/statistical methods and synthetic data engineered to reflect
real domain relationships. It combines a supervised risk classifier, three
distinct anomaly-detection algorithms, local OCR, and a rule-based fusion
engine to answer four questions continuously: what is at risk, why, what
happens next, and where the root cause likely is. No paid API, cloud
service, or hardware sensor is used anywhere in the system.

## Introduction

Restaurants and hotels handle large volumes of perishable inventory with
manual, reactive safety tracking — expiry dates checked by memory or
spreadsheet, storage conditions logged inconsistently if at all, and no
institutional memory of which suppliers repeatedly cause problems. Physical
food-safety inspections are infrequent and cannot catch daily operational
drift. FoodGuard addresses this as a data and algorithms problem: given the
data a kitchen already generates (deliveries, storage logs, consumption,
labels), can risk be predicted and anomalies caught before they become
incidents?

## Problem Statement

Build a software-only system that:
1. Predicts the probability a food batch will become unsafe, with an
   explainable basis.
2. Detects abnormal storage-unit behavior before a hard threshold is
   crossed.
3. Detects supplier behavior that deviates from that supplier's own
   history.
4. Detects label/batch-code inconsistencies indicative of fraud.
5. Detects correlated multi-item failures attributable to one root cause.
6. Routes every finding to the correct department with an explicit,
   auditable action.

## Existing System

Manual tracking (memory, whiteboards, spreadsheets) or single-purpose
expiry-tracker apps that check one date against one threshold. Neither
incorporates storage conditions, supplier history, cross-batch correlation,
or fraud signals, and neither is forward-looking (predictive) rather than
purely reactive.

## Proposed System

A locally-hosted stack: PostgreSQL for structured history, a synthetic data
generator encoding domain-realistic relationships, three independent
ML/statistical models plus three rule-based anomaly checks, a fusion engine
that routes findings by priority and department, a FastAPI backend, a React
dashboard, and a WebSocket channel that pushes live updates on every
detection pass — no polling, no manual refresh.

## Objectives

- Genuine ML/algorithmic depth across multiple distinct techniques
  (classification, time-series changepoint detection, per-entity anomaly
  detection, correlation analysis, rule-based consistency checking) rather
  than one model doing everything.
- Full transparency about synthetic data: every metric is labeled
  `DATA_SOURCE = SYNTHETIC` and never presented as real-world validation.
- Zero cost, zero cloud dependency, fully reproducible on a laptop.
- A live, controllable demo (scenario triggers) rather than a static
  screenshot.

## Requirements

**Software**: Python 3.11, PostgreSQL 16 (Docker), Node 24, Tesseract OCR —
all free/open-source, installed via Homebrew/npm/pip, no accounts.
**Hardware**: any laptop capable of running Docker/Colima; no sensors, no
embedded devices, no physical integration of any kind.

## Architecture

See `docs/ARCHITECTURE.md` for the full diagram and request-flow traces.
In summary: React frontend ↔ FastAPI backend ↔ {pipeline/fusion services,
ML models, anomaly detectors, OCR} ↔ PostgreSQL, with a WebSocket
broadcast layer for live updates.

## Database Design

21 tables covering users/roles, food categories/items/batches, suppliers
and their deliveries, storage units and readings, consumption and wastage
records, label scans, risk predictions, five distinct anomaly-finding
tables, fused incidents, an audit log, and model version metadata. Full
schema in `backend/app/models/`, migrations in `backend/alembic/versions/`.

## Algorithms

| Component | Algorithm | Why this one |
|---|---|---|
| Food-risk prediction | XGBoost classifier (RandomForest fallback) | Handles non-linear interactions between 14 heterogeneous features; feature importances give free explainability |
| Storage anomaly | Rolling baseline + Simple Exponential Smoothing forecast + one-sided CUSUM + linear trend | CUSUM catches *persistent* shifts a single-point z-score would miss; trend fit gives a days-to-breach estimate for proactive maintenance |
| Supplier anomaly | Isolation Forest, fit per-supplier | Judges a delivery against that supplier's *own* baseline, not a population-wide threshold — the whole point of the detector |
| Consumption anomaly | Rolling z-score | Deliberately simple and explainable; this signal cross-references, never overrides, the ML risk score |
| Label/fraud checks | Rule-based (mfg<expiry, shelf-life-vs-category norm, duplicate batch-code reuse) | A fraud/audit finding must be defensible, not a black-box score |
| Unit-failure detection | Pearson correlation of co-rising risk trajectories | Reduces N independent alerts to 1 attributed root-cause incident |
| Fusion | Priority-ordered rule table | Keeps every dimension visible while still producing one actionable routed decision |

## ML Methodology

Full detail in `docs/ML.md`, including the explicit synthetic-label
methodology for the food-risk classifier (a documented weighted formula
combining expiry proximity, perishability, cumulative temperature
exposure, storage deviation, supplier reliability, rejection rate,
consumption drop, and historical incidents, plus Gaussian noise), why
Prophet was replaced with statsmodels, and the honestly-disclosed
near-perfect ROC-AUC caveat (the model recovers a synthetic label it was
trained to predict — this measures label-recoverability, not real-world
food-safety accuracy).

## Feature Engineering

14 features per batch, computed identically at training and inference time
via `app/ml/food_risk/features.py::build_feature_frame` — no train/serve
skew. Includes engineered signals like cumulative degree-hours out of
storage range and consecutive-hours-currently-out-of-range, not just raw
sensor values.

## Implementation

Backend: FastAPI, SQLAlchemy, Alembic, scikit-learn, XGBoost, statsmodels,
pytesseract. Frontend: React 19, TypeScript, Vite, Tailwind CSS v4,
Recharts, react-router-dom. Database: PostgreSQL 16 via Docker Compose.
Auth: JWT with bcrypt password hashing (called directly, bypassing a
known passlib/bcrypt version incompatibility discovered and documented
during development). All local; the `.env` file contains no API keys.

## Testing Methodology

15 automated tests: 11 pure algorithm-level unit tests (fusion routing
logic, CUSUM changepoint detection, unit-failure correlation) requiring no
database, and 1 end-to-end test against the real Postgres instance proving
the unit-failure detector's full DB-to-Incident wiring, with cleanup so
repeated runs don't pollute demo data. All verified stable across repeated
runs (a real test-isolation bug was found and fixed during development —
see git history). Beyond automated tests, every model and detector was
manually verified against its corresponding synthetic scenario before
being marked complete (e.g. confirming FRIDGE_03's drift is flagged while
FRIDGE_01 stays clean, confirming the exact injected supplier anomaly is
isolated with matching deviating features).

## Performance Metrics

Food-risk classifier (on synthetic training data, 20,000 rows, 80/20
split): precision 0.96, recall 0.95, F1 0.95, ROC-AUC 0.999 (see ML.md for
why this number is expected to be this high and what it does and doesn't
prove). Storage/supplier/consumption anomaly detectors validated
qualitatively against known-injected scenarios rather than a held-out
labeled anomaly dataset, since no such real dataset exists for this
domain — this is stated as a limitation, not hidden.

## Results

The system correctly and reproducibly: flags a drifting fridge before it
breaches threshold with a days-to-breach estimate; isolates an anomalous
supplier delivery against its own historical baseline with the exact
deviating features named; catches a batch code reused 100+ days apart with
an inconsistent shelf life; routes a consumption anomaly to investigation
without ever auto-declaring food unsafe on that signal alone; and
correlates co-rising risk across multiple batches in one storage unit into
a single attributed maintenance incident.

## Limitations

1. All data is synthetic; no real hotel/restaurant/supplier data was used
   or is claimed anywhere.
2. The near-perfect classifier metrics reflect a model recovering its own
   synthetic training label, not validated real-world accuracy.
3. The data generator does not transition old batches out of `IN_STOCK`,
   so long simulation runs accumulate an unrealistic backlog.
4. Unit-failure detection requires risk scores to progress across pipeline
   runs to fire — a single instantaneous run against static data correctly
   produces no finding.
5. `/ws/live` does not currently enforce JWT auth on the socket itself.
6. OCR accuracy depends heavily on image quality; low-resolution or
   synthetic-font test images produce poor extraction (real product-label
   photos perform much better).

## Backup / Fallback Approaches Taken

XGBoost import is guarded with a fallback to RandomForestClassifier if the
native library fails to load (a real, encountered issue: `libomp` missing
on macOS). Prophet was dropped in favor of statsmodels'
SimpleExpSmoothing after assessing Prophet's cmdstan build as an
unreliable dependency for a student laptop setup — decided proactively,
not after a failure.

## Future Enhancements

Real IoT/smart-meter log ingestion (explicitly out of scope now to keep
the project hardware-free); SHAP-based explainability in place of raw
feature importances; a genuine time-advancing replay engine so unit-failure
correlation can be demonstrated as a single continuous live run;
JWT-authenticated WebSocket connections; batch lifecycle transitions
(CONSUMED/DISCARDED) in the data generator for longer-running realism.

## Conclusion

FoodGuard demonstrates that a small team can build genuine ML and
algorithmic depth — supervised classification, time-series changepoint
detection, per-entity anomaly detection, correlation analysis, and
rule-based fraud checking — into a coherent, explainable, fully local
system addressing a real operational problem, without any paid service,
API key, or physical hardware.
