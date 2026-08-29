# FoodGuard — Offline Verification

Genuinely tested, not just asserted: ran every core flow with
`http_proxy`/`https_proxy`/`HTTP_PROXY`/`HTTPS_PROXY` all pointed at
`http://127.0.0.1:1` (a port nothing listens on, so any outbound HTTP/HTTPS
call fails immediately instead of timing out slowly or silently succeeding
via a real network path).

## Checklist and result

| Flow | Result under broken proxy |
|---|---|
| `scripts/generate_demo_data.py --scenario normal` | ✅ Works, 80 batches seeded |
| `app.services.pipeline.run_full_pipeline` (ML models + all anomaly detectors) | ✅ Works, incidents produced |
| FastAPI startup (`uvicorn app.main:app`) | ✅ Starts clean, no hang |
| `POST /api/auth/login` (bcrypt + JWT) | ✅ Works |
| `GET /api/dashboard/summary` (Postgres aggregate queries) | ✅ Works |
| `POST /api/ocr/scan` (local Tesseract) | ✅ Works, real OCR text extracted |

## Static audit (grep, backend + frontend source only, excluding vendored deps)

- No `http://` / `https://` literals pointing anywhere but `127.0.0.1` /
  `localhost` (the CORS allowlist and the API/WS base URLs).
- No `import requests`, `import httpx`, or `urllib.request` usage in
  `backend/app/`.
- No `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` /
  `GOOGLE_CLOUD_API_KEY` / `AWS_ACCESS_KEY` / `AZURE_KEY` referenced
  anywhere in project source (two hits in vendored `pydantic_settings` and
  `pandas` test fixtures — third-party library internals, never invoked).

## Not covered by this check

- The frontend's `npm run dev`/`npm run build` steps themselves need
  network the *first* time (`npm install`) — already done, not re-tested
  offline, and not a runtime dependency.
- Browser-side: the built frontend was not run inside an actual airplane-mode
  browser this session (no browser extension connected to visually verify)
  — the audit above covers what URLs the frontend code could possibly call,
  which is only the local API/WS base URLs.
