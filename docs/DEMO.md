# FoodGuard — Demo Script

## Setup (do this before the review, not during it)

```bash
# 1. Postgres (docker/colima must be running)
cd foodguard && docker compose up -d

# 2. seed baseline data
backend/venv/bin/python scripts/generate_demo_data.py --scenario normal --days 90

# 3. train the model once (only needed the first time / after deleting models/)
cd backend && venv/bin/python -m app.ml.food_risk.train --n 20000 && cd ..

# 4. start backend
cd backend && venv/bin/uvicorn app.main:app --port 8000 &

# 5. start frontend
cd frontend && npm run dev -- --port 5173 &
```

Open `http://localhost:5173`, log in as `manager@foodguard.internal` /
`demo1234`.

**Disconnect the internet now if you want to prove the "100% local"
claim** — nothing above touches the network except the initial `npm
install`/`pip install`, already done.

## Scenario 1 — Normal operation (baseline credibility)

Just show the Dashboard, Inventory, Storage, Suppliers pages with the
`normal` scenario loaded. Point out: real Postgres-backed data, real risk
scores with explainable top-5 factors per batch, nothing hardcoded.

## Scenario 2 — Fridge drift (storage anomaly, proactive detection)

On the Dashboard, pick `fridge_drift` from the scenario dropdown, click
**Trigger scenario (live)**. Narrate while it runs (~5-10s):
"This regenerates 90 days of sensor history where FRIDGE_03 is slowly
warming — 0.38°C/day for the last 8 days — and reruns the full detection
pipeline." When the toast says "complete," go to **Storage**: FRIDGE_03
shows a `TEMPERATURE_DRIFT`/`CUSUM_SHIFT` banner with an estimated
days-to-threshold, while FRIDGE_01 stays clean. This is the "catch it
before it crosses the line" claim — show the trend, not just a breach.

## Scenario 3 — Supplier anomaly (per-supplier baseline, not global)

Trigger `supplier_anomaly`. Go to **Suppliers**: CoastalCatch Seafood
shows HIGH severity with the exact deviating features (batch size down,
delay up, defect rate up) — z-scored against *that supplier's own*
history, not a population-wide threshold. Point out another supplier with
a slightly-off delivery stays LOW/normal — the model isn't just flagging
anything unusual, it's flagging unusual-for-that-supplier.

## Scenario 4 — Label/batch-code fraud

Trigger `label_fraud`. Go to **Incidents**, filter by `AUDIT` department:
shows `FRAUD_REVIEW` incidents with reason codes `POSSIBLE_BATCH_REUSE`
and `INCONSISTENT_SHELF_LIFE` — a batch code planted on day 2, reused
~100 days later with an inflated shelf life. This demonstrates the
fraud-detection dimension is separate from and takes priority over the
food-risk score (see fusion priority order in ARCHITECTURE.md).

## Scenario 5 — Live label scan (real OCR, no cloud)

Go to **Label Scanner**, upload a real photo of a packaged food label (a
photo works far better than a screen-rendered test image — bring a real
product). Show the raw OCR text, extracted fields, and the duplicate-batch
heads-up check running against the live DB.

## Scenario 6 — Consumption anomaly (cross-referenced, not auto-unsafe)

Trigger `consumption_drop`. Go to **Incidents**, filter by
`INVESTIGATION` department: shows a `CONSUMPTION_ANOMALY` incident (staff
quietly avoiding an item) explicitly routed to `INVESTIGATE`, never
`DO_NOT_SERVE` — point out `test_consumption_anomaly_never_auto_declares_unsafe`
in the test suite as the guardrail for this.

## Scenario 7 — Unit-level correlated failure (if time allows)

This one needs risk *progression*, not a single trigger (see ML.md). To
show it live: trigger `unit_failure`, then trigger it again a minute
later (or point to `tests/e2e/test_unit_failure_pipeline.py`, which proves
the wiring directly against Postgres with seeded progressing risk scores)
— be upfront that showing this live end-to-end needs the pipeline to run
across genuinely advancing time, and the e2e test is the honest proof
of correctness in the meantime.

## Backend-only fallback (if the frontend has a demo-day problem)

Everything above is also directly checkable via `curl` — see `docs/API.md`
for exact endpoints. The FastAPI auto-docs at `http://127.0.0.1:8000/docs`
(Swagger UI) can drive every request from a browser too, no custom
frontend required, if things go sideways.

## Closing points for the panel

- Every number on screen traces to a real algorithm: XGBoost classifier,
  CUSUM changepoint detection, per-supplier Isolation Forest, Pearson
  correlation, rule-based fraud checks — not one AI-API call anywhere.
- `DATA_SOURCE = SYNTHETIC` is disclosed everywhere it matters (README,
  ML.md, generator output, training logs) — say this proactively, don't
  wait to be asked.
- Zero paid services, zero API keys, runs fully offline after setup.
