from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, dashboard, incidents, inventory, ocr, pipeline, simulation, storage, suppliers

app = FastAPI(
    title="FoodGuard API",
    description="ML-based food safety risk prediction and multi-source anomaly detection. "
                 "100% local: no paid APIs, no API keys, no mandatory internet at runtime.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(inventory.router)
app.include_router(storage.router)
app.include_router(suppliers.router)
app.include_router(incidents.router)
app.include_router(pipeline.router)
app.include_router(ocr.router)
app.include_router(simulation.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "data_source": "SYNTHETIC (demo mode)"}
