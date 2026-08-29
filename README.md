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

## Not yet built (honest status, next steps)

- **REST API** (FastAPI routes) — the pipeline/services layer underneath is
  done and tested directly in Python; no HTTP layer wired yet.
- **Auth** (JWT + roles) — models exist (`users.py`, `RoleEnum`), no login
  flow yet.
- **Correlated unit-failure detection** — algorithm implemented
  (`app/anomaly/unit_failure.py`) but needs multi-run risk history to have
  anything to correlate; not wired into the single-pass pipeline yet.
- **WebSocket replay engine** (Phase 21, the "no hardware, live simulation"
  piece) — not started.
- **React frontend** — not started.
- **OCR label-scanning endpoint** — Tesseract is installed and ready, no
  endpoint wraps it yet.
- **docs/ARCHITECTURE.md, API.md, DEMO.md, PROJECT_REPORT.md** — not yet
  written (only ML.md and this README exist so far).
- **Offline end-to-end check** — not run yet (nothing to check without the
  API/frontend running).

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
