"""
E2E test proving the manual-entry API endpoints actually score what was
just submitted, against the real (dockerized) Postgres via the real
FastAPI app (httpx ASGI transport, no network socket needed).

This directly guards against the commit-ordering bug found during manual
verification: pd.read_sql(text(...), db.bind) opens a separate raw
connection off the engine that can't see a flushed-but-uncommitted row
from the request's ORM session, so scoring a just-created row silently
returned nothing unless the create was committed first.
"""
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.database.session import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def _schema():
    Base.metadata.create_all(bind=engine)


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/auth/login", json={"email": "manager@foodguard.internal", "password": "demo1234"})
    if resp.status_code != 200:
        # demo account may not exist yet on a fresh DB -- register it
        await client.post("/api/auth/register", json={
            "email": "manager@foodguard.internal", "full_name": "Demo Manager",
            "password": "demo1234", "role": "MANAGER",
        })
        resp = await client.post("/api/auth/login", json={"email": "manager@foodguard.internal", "password": "demo1234"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_manual_batch_creation_returns_a_real_scored_risk(_schema):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        categories = (await client.get("/api/manual/reference/categories", headers=headers)).json()
        suppliers = (await client.get("/api/manual/reference/suppliers", headers=headers)).json()
        units = (await client.get("/api/manual/reference/storage-units", headers=headers)).json()

        if not categories or not suppliers or not units:
            pytest.skip("No reference data seeded -- run generate_demo_data.py first")

        resp = await client.post("/api/manual/batches", headers=headers, json={
            "new_food_item_name": "E2E Test Item",
            "category_id": categories[0]["id"],
            "supplier_id": suppliers[0]["id"],
            "storage_unit_id": units[0]["id"],
            "batch_code": "E2E-COMMIT-ORDER-TEST",
            "quantity": 5,
            "manufacturing_date": "2020-01-01",   # deliberately long-expired -> should score HIGH
            "expiry_date": "2020-01-05",
        })
        assert resp.status_code == 200
        body = resp.json()

        # This is the exact assertion that would have caught the commit-ordering
        # bug: risk_prediction and incident must NOT be null for a batch that
        # was just created and immediately scored.
        assert body["risk_prediction"] is not None, "risk scoring returned nothing for a just-created batch"
        assert body["risk_prediction"]["risk_class"] == "HIGH"
        assert body["incident"] is not None
        assert body["incident"]["action"] == "DO_NOT_SERVE"

        _cleanup(body["created_id"])


def _cleanup(batch_id: str):
    """This hits the real demo DB, not a throwaway fixture -- remove what it created."""
    from sqlalchemy import text as sql_text

    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        db.execute(sql_text("DELETE FROM incidents WHERE source_id=:b"), {"b": batch_id})
        db.execute(sql_text("DELETE FROM risk_predictions WHERE food_batch_id=:b"), {"b": batch_id})
        food_item_id = db.execute(sql_text("SELECT food_item_id FROM food_batches WHERE id=:b"), {"b": batch_id}).scalar()
        db.execute(sql_text("DELETE FROM food_batches WHERE id=:b"), {"b": batch_id})
        if food_item_id:
            db.execute(sql_text("DELETE FROM food_items WHERE id=:f"), {"f": str(food_item_id)})
        db.commit()
    finally:
        db.close()
