# FoodGuard

**ML-Based Food Safety Risk Prediction and Multi-Source Anomaly Detection System**

100% local. Zero paid APIs, zero API keys, zero mandatory internet at runtime.
See `docs/ML.md` for methodology and honest limitations, `docs/ARCHITECTURE.md`
for the system diagram, `docs/DEMO.md` for the exact demo script.

## What's built and verified (this session)

- **Environment**: Colima + Docker (Postgres container, port 5433), pyenv
  Python 3.11.9 venv (avoids ML-lib wheel issues on newer Python), Tesseract
  OCR installed locally, all via Homebrew — no cloud accounts anywhere.
- **Database**: 21-table PostgreSQL schema via SQLAlchemy + Alembic
  (users, food categories/items/batches, suppliers/deliveries, storage
  units/readings, consumption/wastage, label scans, risk predictions, 5
  anomaly types, incidents, audit logs, model versions). Migration applied
  and verified.
- **Synthetic data generator**: `scripts/generate_demo_data.py`, 6 scenarios
  (normal, fridge_drift, supplier_anomaly, unit_failure, label_fraud,
  consumption_drop), domain-realistic distributions, `DATA_SOURCE=SYNTHETIC`
  disclosed everywhere.
- **ML Model #1** (food-risk XGBoost): trained, saved, versioned in
  `models/food_risk/`.
- **ML Model #2** (storage drift: rolling baseline + exp-smoothing + CUSUM +
  trend): verified against the fridge_drift scenario.
- **ML Model #3** (supplier Isolation Forest, per-supplier baseline):
  verified against the supplier_anomaly scenario.
- **Consumption anomaly** (rolling z-score) and **label/fraud consistency
  checks** (mfg/expiry, shelf-life norms, duplicate batch-code reuse):
  both implemented and verified against their respective scenarios.
- **Fusion engine**: routes every finding to a department
  (Kitchen/Maintenance/Procurement/Audit/Investigation) with an explicit
  priority order; 11 passing unit tests cover the routing logic and the
  storage-drift math.
- **Full pipeline** (`app/services/pipeline.py`): DB → features → all
  models/anomaly engines → fusion → `incidents` table, run end-to-end and
  verified against real data in Postgres.

## Also built since the above (REST API, live-sim, frontend, unit-failure)

- **REST API** (FastAPI): auth (JWT+roles), dashboard summary, inventory,
  storage, suppliers, incidents (+resolve), pipeline trigger, OCR scan —
  all smoke-tested live end-to-end.
- **WebSocket live-sim** (`/ws/live` + `/api/simulation/trigger`):
  regenerates a scenario, reruns the pipeline, pushes the result to every
  connected dashboard with no polling. Verified live.
- **React + TypeScript + Tailwind frontend**: Login, Dashboard, Inventory,
  Storage, Suppliers, Incidents, Label Scanner — wired to the live API and
  the WebSocket feed. `tsc` and production build both clean.
- **Correlated unit-failure detection**: wired into the pipeline
  (`run_unit_failure_detection`), verified both at the algorithm level and
  via an e2e DB test. See `docs/ML.md` for the honest caveat on when it
  actually fires (needs risk progression across runs, not two static ones).

## Not yet built (honest status, next steps)

- **docs/ARCHITECTURE.md, API.md, DEMO.md, PROJECT_REPORT.md** — not yet
  written (only ML.md and this README exist so far).
- **Offline end-to-end check** — not run yet.
- Frontend has not been visually verified in an actual browser this
  session (no browser extension connected) — build/typecheck/API-integration
  all pass, but eyeball it yourself before the review.

## Quick start (what works today)

```bash
# 1. start local Postgres
docker compose up -d

# 2. install deps (already done in this repo's backend/venv)
cd backend && venv/bin/pip install -r requirements.txt

# 3. apply migrations
venv/bin/alembic upgrade head

# 4. generate synthetic demo data (pick a scenario)
cd .. && backend/venv/bin/python scripts/generate_demo_data.py --scenario fridge_drift --days 90

# 5. train the food-risk model
backend/venv/bin/python -m app.ml.food_risk.train --n 20000   # run from backend/

# 6. run the full detection pipeline against the seeded data
backend/venv/bin/python -c "
from app.database.session import SessionLocal
from app.services.pipeline import run_full_pipeline
print(run_full_pipeline(SessionLocal()))
"

# 7. run the unit tests
cd backend && venv/bin/python -m pytest tests/unit -v
```
