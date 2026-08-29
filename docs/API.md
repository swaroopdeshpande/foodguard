# FoodGuard — API Reference

Base URL: `http://127.0.0.1:8000`. All routes except `/api/health`,
`/api/auth/login`, `/api/auth/register` require `Authorization: Bearer <JWT>`.

## Auth

### `POST /api/auth/register`
Body: `{ email, full_name, password, role? }` (role defaults to `KITCHEN`;
one of `ADMIN/MANAGER/KITCHEN/PROCUREMENT/MAINTENANCE/AUDITOR`).
Returns: `{ id, email, full_name, role }`.
Open for the demo — see security note in `auth.py`; would be ADMIN-only in
a real deployment.

### `POST /api/auth/login`
Body: `{ email, password }`. Returns `{ access_token, token_type, role }`.
Demo accounts (recreated on every `generate_demo_data.py` reset):
`admin@foodguard.internal`, `manager@foodguard.internal`,
`kitchen@foodguard.internal` — password `demo1234`.

## Dashboard

### `GET /api/dashboard/summary`
Returns aggregate counts: `total_batches_in_stock`, `high_risk_batches`,
`open_incidents`, `incidents_by_department`, `incidents_by_action`,
`estimated_wastage_loss`, `active_storage_anomalies` (24h),
`active_supplier_anomalies` (7d).

## Inventory

### `GET /api/inventory/batches`
Query params (all optional): `category`, `supplier`, `risk_class`
(`LOW/MEDIUM/HIGH`), `limit` (default 100). Returns each IN_STOCK batch
joined with its latest risk prediction (probability, class, top-5 factors).

## Storage

### `GET /api/storage/units`
Returns every storage unit with its most recent temperature reading and
most recent `StorageAnomaly` (type/severity/estimated days-to-threshold).

## Suppliers

### `GET /api/suppliers`
Returns every supplier with its most recent `SupplierAnomaly` score,
severity, and the specific deviating features (z-scores vs that supplier's
own baseline).

## Incidents

### `GET /api/incidents`
Query params: `department`, `severity`, `status`, `limit` (default 100).
Returns fused incidents newest-first.

### `POST /api/incidents/{id}/resolve`
Marks one incident `RESOLVED` with a timestamp. Returns the updated incident.

## Pipeline (ADMIN/MANAGER only)

### `POST /api/pipeline/run`
Runs the full detection pipeline once, synchronously, against current DB
state. Returns `{ food_risk_incidents, storage_incidents,
supplier_incidents, consumption_incidents, unit_failure_incidents }`.

## Simulation / live updates

### `WS /ws/live`
No query params; auth is not currently enforced on the socket itself (demo
scope — see Limitations). On connect, sends
`{ type: "CONNECTED", scenario, running_job, last_result }`. Subsequently
pushes `SCENARIO_STARTED` / `SCENARIO_COMPLETE` (with `pipeline_result`) /
`SCENARIO_FAILED` (with truncated stderr) — no polling required.

### `POST /api/simulation/trigger` (ADMIN/MANAGER only)
Body: `{ scenario, days }` — scenario one of `normal / fridge_drift /
supplier_anomaly / unit_failure / label_fraud / consumption_drop`.
Regenerates the DB with that scenario (subprocess) then runs the full
pipeline, broadcasting progress over `/ws/live`. Returns immediately with
`{ status: "started" | "already_running", scenario, days }`.

### `GET /api/simulation/status`
Returns current scenario, whether a job is running, last run timestamp,
last pipeline result, and number of connected WebSocket clients.

## OCR

### `POST /api/ocr/scan`
Multipart form, field `file` (PNG/JPEG). Runs local Tesseract OCR, parses
mfg/expiry dates and batch code via regex, checks the batch code against
existing history for a pre-confirm duplicate heads-up, persists a
`LabelScan` row. Returns `{ raw_ocr_text, extracted_fields,
ocr_confidence, anomalies }`.

## Health

### `GET /api/health`
No auth. `{ status: "ok", data_source: "SYNTHETIC (demo mode)" }`.

## Known gaps (say these in the report)

- `/ws/live` doesn't check the JWT — anyone who can reach the port sees
  simulation events. Fine for a local single-user demo, not for a real
  deployment (would need a token query param or WS auth handshake).
- No pagination beyond `limit` — fine at demo data scale (hundreds of rows),
  would need real pagination for a production-sized dataset.
- `/api/auth/register` is open, not ADMIN-gated (see auth.py comment).
