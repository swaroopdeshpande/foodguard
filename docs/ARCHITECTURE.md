# FoodGuard — Architecture

## System diagram

```
                         ┌─────────────────────────────┐
                         │   React + TS frontend (Vite)│
                         │  Dashboard / Inventory /    │
                         │  Storage / Suppliers /      │
                         │  Incidents / Label Scanner  │
                         └───────────┬─────────┬───────┘
                                     │ HTTPS   │ WebSocket
                                     │ REST    │ /ws/live
                         ┌───────────▼─────────▼───────┐
                         │      FastAPI backend         │
                         │  app/api/routes/*.py         │
                         │  JWT auth, role-gated routes  │
                         └───────────┬───────────────────┘
                                     │
                 ┌───────────────────┼────────────────────┐
                 │                   │                    │
        ┌────────▼────────┐ ┌────────▼────────┐ ┌─────────▼────────┐
        │ app/services/    │ │ app/ml/         │ │ app/anomaly/      │
        │ pipeline.py      │ │ food_risk/      │ │ storage_drift.py  │
        │ fusion.py        │ │ supplier_anomaly│ │ consumption.py    │
        │ simulation.py    │ │                 │ │ label_fraud.py    │
        │                  │ │                 │ │ unit_failure.py   │
        └────────┬─────────┘ └────────┬────────┘ └─────────┬─────────┘
                 │                    │                    │
                 └──────────┬─────────┴──────────┬─────────┘
                            │                    │
                   ┌────────▼────────┐  ┌────────▼─────────┐
                   │  app/ocr/       │  │  PostgreSQL (docker)│
                   │  extractor.py   │  │  21 tables          │
                   │  (Tesseract)    │  │  via SQLAlchemy+    │
                   │                 │  │  Alembic            │
                   └─────────────────┘  └─────────────────────┘
```

## Request flows

### 1. Normal read (e.g. Dashboard)
`React → GET /api/dashboard/summary (JWT) → FastAPI route → raw SQL
aggregate queries → Postgres → JSON → React state → Recharts`

### 2. Scenario trigger (the "live simulation" path)
```
React "Trigger scenario" button
   → POST /api/simulation/trigger {scenario, days}
   → FastAPI schedules an asyncio background task, returns immediately
   → subprocess: scripts/generate_demo_data.py --scenario X --days N
        (drops/recreates all 21 tables, seeds domain-realistic synthetic data,
         re-seeds 3 demo user accounts)
   → app.services.pipeline.run_full_pipeline(db) runs in a thread:
        run_food_risk        -> RiskPrediction + LabelAnomaly + Incident rows
        run_storage_anomalies -> StorageAnomaly + Incident rows
        run_supplier_anomalies -> SupplierAnomaly + Incident rows
        run_consumption_anomalies -> ConsumptionAnomaly + Incident rows
        run_unit_failure_detection -> UnitIncident + Incident rows
   → ConnectionManager.broadcast({"type": "SCENARIO_COMPLETE", ...})
        pushed to every WebSocket client connected to /ws/live
   → React's useLiveSocket hook receives it, dispatches a "fg:refresh"
     window event, every page's useEffect refetches — no manual reload
```

### 3. Label scan
`React file upload → POST /api/ocr/scan (multipart) → pytesseract (local
Tesseract binary) → regex field extraction → duplicate-batch-code heads-up
check against Postgres → LabelScan row persisted → JSON response`

## Why this shape

- **Fusion engine as a single choke point** (`app/services/fusion.py`):
  every detector (ML model or anomaly rule) produces a severity/probability,
  but only `fuse()` decides the `action` + `department`. This is what keeps
  the "5 independent alerts vs 1 attributed incident" behavior consistent
  and testable in isolation (11 pure unit tests, no DB needed).
- **Anomaly detectors are pure functions of DataFrames/Series**
  (`analyze_unit_series`, `score_latest_delivery`, `detect_consumption_anomaly`,
  `detect_unit_incident`) — `pipeline.py` is the only place that touches SQL
  and turns their output into rows. This is why the algorithm-level unit
  tests never need Postgres, only the pipeline-wiring tests do.
- **The generator and the pipeline are decoupled**: `generate_demo_data.py`
  never calls into `app.services.pipeline`, and vice versa. The simulation
  layer glues them together with a subprocess boundary specifically so the
  generator's own DB engine/session never collides with the API process's.
- **No model is loaded on every request**: `MODEL_LATEST` points at a
  `models/food_risk/latest.json` pointer file, loaded once per pipeline run
  — swapping in a retrained model is just overwriting that file, no code
  change, no API restart needed.
