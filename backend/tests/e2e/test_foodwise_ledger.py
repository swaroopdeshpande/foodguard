"""
E2E tests for FoodWise's core design rule: current stock is ALWAYS
ledger-derived, hard expiry/quarantine controls are enforced, and FEFO
recommendations never surface DEMO data as real usable inventory.

Runs against the real (dockerized) Postgres via the FastAPI app.
"""
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def _schema():
    Base.metadata.create_all(bind=engine)


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/auth/login", json={"email": "manager@foodguard.internal", "password": "demo1234"})
    if resp.status_code != 200:
        await client.post("/api/auth/register", json={
            "email": "manager@foodguard.internal", "full_name": "Demo Manager",
            "password": "demo1234", "role": "MANAGER",
        })
        resp = await client.post("/api/auth/login", json={"email": "manager@foodguard.internal", "password": "demo1234"})
    return resp.json()["access_token"]


@pytest_asyncio.fixture()
async def client_and_headers(_schema):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        categories = (await client.get("/api/manual/reference/categories", headers=headers)).json()
        suppliers = (await client.get("/api/manual/reference/suppliers", headers=headers)).json()
        units = (await client.get("/api/manual/reference/storage-units", headers=headers)).json()
        if not categories or not suppliers or not units:
            pytest.skip("No reference data seeded -- run generate_demo_data.py first")

        yield client, headers, categories[0]["id"], suppliers[0]["id"], units[0]["id"]


async def _create_batch(client, headers, cat_id, sup_id, unit_id, qty=40, days_to_expiry=5, batch_code=None):
    resp = await client.post("/api/foodwise/deliveries", headers=headers, json={
        "new_food_item_name": f"E2E Ledger Item {uuid.uuid4().hex[:6]}",
        "category_id": cat_id, "supplier_id": sup_id, "storage_unit_id": unit_id,
        "batch_code": batch_code or f"E2E-{uuid.uuid4().hex[:8]}",
        "quantity": qty, "manufacturing_date": str(date.today()),
        "expiry_date": str(date.today() + timedelta(days=days_to_expiry)),
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_consumption_and_waste_correctly_decrement_ledger(client_and_headers):
    client, headers, cat_id, sup_id, unit_id = client_and_headers
    batch = await _create_batch(client, headers, cat_id, sup_id, unit_id, qty=40)
    batch_id = batch["batch_id"]
    assert batch["current_quantity"] == 40.0

    r1 = await client.post("/api/foodwise/consumption", headers=headers, json={"food_batch_id": batch_id, "quantity": 8})
    assert r1.json()["remaining_quantity"] == 32.0

    r2 = await client.post("/api/foodwise/consumption", headers=headers, json={"food_batch_id": batch_id, "quantity": 10})
    assert r2.json()["remaining_quantity"] == 22.0

    r3 = await client.post("/api/foodwise/waste", headers=headers, json={
        "food_batch_id": batch_id, "quantity": 3, "reason": "spoilage",
    })
    assert r3.json()["remaining_quantity"] == 19.0

    _cleanup(batch_id)


@pytest.mark.asyncio
async def test_cannot_consume_more_than_available(client_and_headers):
    client, headers, cat_id, sup_id, unit_id = client_and_headers
    batch = await _create_batch(client, headers, cat_id, sup_id, unit_id, qty=5)

    resp = await client.post("/api/foodwise/consumption", headers=headers, json={
        "food_batch_id": batch["batch_id"], "quantity": 999,
    })
    assert resp.status_code == 400
    _cleanup(batch["batch_id"])


@pytest.mark.asyncio
async def test_expired_batch_blocks_normal_consumption_but_allows_authorized_override(client_and_headers):
    client, headers, cat_id, sup_id, unit_id = client_and_headers
    batch = await _create_batch(client, headers, cat_id, sup_id, unit_id, qty=10, days_to_expiry=-3)

    blocked = await client.post("/api/foodwise/consumption", headers=headers, json={
        "food_batch_id": batch["batch_id"], "quantity": 2,
    })
    assert blocked.status_code == 400
    assert "expired" in blocked.json()["detail"].lower()

    allowed = await client.post("/api/foodwise/consumption", headers=headers, json={
        "food_batch_id": batch["batch_id"], "quantity": 2,
        "allow_expired_override": True, "override_reason": "Manager approved",
    })
    assert allowed.status_code == 200
    assert allowed.json()["remaining_quantity"] == 8.0
    _cleanup(batch["batch_id"])


@pytest.mark.asyncio
async def test_quarantine_blocks_consumption_and_release_restores_it(client_and_headers):
    client, headers, cat_id, sup_id, unit_id = client_and_headers
    batch = await _create_batch(client, headers, cat_id, sup_id, unit_id, qty=10)
    batch_id = batch["batch_id"]

    await client.post(f"/api/foodwise/batches/{batch_id}/quarantine", headers=headers, json={"reason": "Suspected spoilage"})

    can_use = await client.get(f"/api/foodwise/batches/{batch_id}/can-use", headers=headers)
    assert can_use.json()["status"] == "DO_NOT_USE"
    assert can_use.json()["can_use"] is False

    blocked = await client.post("/api/foodwise/consumption", headers=headers, json={"food_batch_id": batch_id, "quantity": 1})
    assert blocked.status_code == 400

    await client.post(f"/api/foodwise/batches/{batch_id}/release", headers=headers)
    can_use_after = await client.get(f"/api/foodwise/batches/{batch_id}/can-use", headers=headers)
    assert can_use_after.json()["can_use"] is True

    _cleanup(batch_id)


@pytest.mark.asyncio
async def test_fefo_recommends_earlier_expiring_batch(client_and_headers):
    client, headers, cat_id, sup_id, unit_id = client_and_headers

    item_resp = await client.post("/api/foodwise/deliveries", headers=headers, json={
        "new_food_item_name": f"E2E FEFO Item {uuid.uuid4().hex[:6]}", "category_id": cat_id,
        "supplier_id": sup_id, "storage_unit_id": unit_id, "batch_code": f"FEFO-A-{uuid.uuid4().hex[:6]}",
        "quantity": 10, "manufacturing_date": str(date.today()), "expiry_date": str(date.today() + timedelta(days=10)),
    })
    item_id = item_resp.json()["food_item_id"]
    batch_far = item_resp.json()["batch_id"]

    near_resp = await client.post("/api/foodwise/deliveries", headers=headers, json={
        "food_item_id": item_id, "supplier_id": sup_id, "storage_unit_id": unit_id,
        "batch_code": f"FEFO-B-{uuid.uuid4().hex[:6]}", "quantity": 5,
        "manufacturing_date": str(date.today()), "expiry_date": str(date.today() + timedelta(days=1)),
    })
    batch_near = near_resp.json()["batch_id"]

    fefo = await client.get(f"/api/foodwise/fefo/{item_id}", headers=headers)
    queue = fefo.json()
    assert queue[0]["batch_id"] == batch_near
    assert queue[0]["recommended"] is True
    assert queue[1]["batch_id"] == batch_far
    assert queue[1]["recommended"] is False

    warning = await client.post("/api/foodwise/consumption", headers=headers, json={"food_batch_id": batch_far, "quantity": 1})
    assert warning.json()["fefo_warning"] is not None
    assert "expires earlier" in warning.json()["fefo_warning"]

    _cleanup(batch_far)
    _cleanup(batch_near)


@pytest.mark.asyncio
async def test_use_first_and_fefo_never_include_demo_data(client_and_headers):
    """The real bug found during manual verification: use_first_queue and
    fefo_recommendation initially had no data_source filter, so a hotel's
    real FEFO queue could recommend a synthetic DEMO batch as if it were
    real usable inventory."""
    client, headers, cat_id, sup_id, unit_id = client_and_headers
    batch = await _create_batch(client, headers, cat_id, sup_id, unit_id, qty=10)

    use_first = await client.get("/api/foodwise/use-first", headers=headers)
    from app.database.session import SessionLocal
    from sqlalchemy import text as sql_text
    db = SessionLocal()
    demo_batch_ids = {str(r[0]) for r in db.execute(sql_text(
        "SELECT id FROM food_batches WHERE data_source='DEMO'"
    )).fetchall()}
    db.close()

    returned_ids = {b["batch_id"] for b in use_first.json()}
    assert returned_ids.isdisjoint(demo_batch_ids), "use_first_queue leaked DEMO batches into REAL recommendations"

    _cleanup(batch["batch_id"])


def _cleanup(batch_id: str):
    from sqlalchemy import text as sql_text

    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        db.execute(sql_text("DELETE FROM inventory_transactions WHERE food_batch_id=:b"), {"b": batch_id})
        db.execute(sql_text("DELETE FROM consumption_records WHERE food_batch_id=:b"), {"b": batch_id})
        db.execute(sql_text("DELETE FROM wastage_records WHERE food_batch_id=:b"), {"b": batch_id})
        db.execute(sql_text("DELETE FROM supplier_deliveries WHERE food_batch_id=:b"), {"b": batch_id})
        db.execute(sql_text("DELETE FROM risk_predictions WHERE food_batch_id=:b"), {"b": batch_id})
        food_item_id = db.execute(sql_text("SELECT food_item_id FROM food_batches WHERE id=:b"), {"b": batch_id}).scalar()
        db.execute(sql_text("DELETE FROM food_batches WHERE id=:b"), {"b": batch_id})
        if food_item_id:
            other_batches = db.execute(
                sql_text("SELECT count(*) FROM food_batches WHERE food_item_id=:f"), {"f": str(food_item_id)}
            ).scalar()
            if not other_batches:  # only delete the item once nothing else references it
                db.execute(sql_text("DELETE FROM food_items WHERE id=:f"), {"f": str(food_item_id)})
        db.commit()
    finally:
        db.close()
