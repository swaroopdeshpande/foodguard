"""
E2E test against the real (dockerized) Postgres: proves run_unit_failure_detection
actually wires the algorithm to the DB and produces a routed Incident, using
directly-seeded risk_predictions rows (bypassing the ML model) since the
correlation needs a *progression* over time that a single pipeline pass
against static historical data can't produce on its own -- see ML.md.

Run: backend/venv/bin/python -m pytest tests/e2e -v
Requires: docker compose up -d (uses whatever DB the app is configured for).
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.models.food import FoodBatch, FoodCategory, FoodItem  # noqa: E402
from app.models.incidents import DepartmentEnum, Incident  # noqa: E402
from app.models.risk import RiskPrediction  # noqa: E402
from app.models.storage import StorageUnit  # noqa: E402
from app.models.suppliers import Supplier  # noqa: E402
from app.services.pipeline import run_unit_failure_detection  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _seed_batch_with_rising_risk(db, unit, category, supplier, start_p, end_p, n=6):
    item = FoodItem(name=f"item-{uuid.uuid4().hex[:6]}", category_id=category.id, unit_price=100)
    db.add(item)
    db.flush()

    batch = FoodBatch(
        food_item_id=item.id, supplier_id=supplier.id, storage_unit_id=unit.id,
        batch_code=f"TEST-{uuid.uuid4().hex[:8]}", quantity=10,
        manufacturing_date=datetime.now(timezone.utc).date(),
        expiry_date=datetime.now(timezone.utc).date() + timedelta(days=5),
        status="IN_STOCK",
    )
    db.add(batch)
    db.flush()

    now = datetime.now(timezone.utc)
    for i in range(n):
        p = start_p + (end_p - start_p) * i / (n - 1)
        db.add(RiskPrediction(
            food_batch_id=batch.id, predicted_at=now - timedelta(hours=(n - i)),
            risk_probability=round(p, 4), risk_class="HIGH" if p > 0.6 else "LOW",
            prediction_horizon="now", feature_snapshot={}, top_factors={}, model_version="test",
        ))
    db.flush()
    return batch


def test_unit_failure_detection_creates_routed_incident(db):
    unit = StorageUnit(name=f"TESTUNIT-{uuid.uuid4().hex[:6]}", unit_type="FRIDGE", target_temp_c=4.0)
    category = FoodCategory(
        name=f"cat-{uuid.uuid4().hex[:6]}", perishability_level=5,
        expected_shelf_life_days=5, required_min_temp_c=0, required_max_temp_c=5,
    )
    supplier = Supplier(name=f"sup-{uuid.uuid4().hex[:6]}")
    db.add_all([unit, category, supplier])
    db.flush()

    # 3 batches in the SAME unit, all independently trending toward high risk together
    for start, end in [(0.1, 0.75), (0.15, 0.8), (0.05, 0.7)]:
        _seed_batch_with_rising_risk(db, unit, category, supplier, start, end)
    db.commit()

    incidents = run_unit_failure_detection(db)
    db.commit()

    # Scope to THIS test's unit -- run_unit_failure_detection scans every
    # storage unit in the DB, and prior e2e runs can leave stale test units
    # with their own accumulated risk_predictions history still IN_STOCK,
    # producing incidents for units unrelated to this test.
    ours = [i for i in incidents if i.dimensions_snapshot.get("storage_unit") == unit.name]
    assert len(ours) == 1
    incident = ours[0]
    assert incident.source_type == "UNIT_INCIDENT"
    assert incident.department == DepartmentEnum.MAINTENANCE
    assert incident.dimensions_snapshot["affected_batches"] == 3
    assert incident.dimensions_snapshot["storage_unit"] == unit.name

    # confirm it's actually persisted, not just returned in-memory
    persisted = db.query(Incident).filter(Incident.id == incident.id).first()
    assert persisted is not None
    assert persisted.status == "OPEN"

    _cleanup(db, unit.id)


def _cleanup(db, unit_id):
    """This test runs against the real (dockerized) demo DB, not a throwaway
    fixture DB -- clean up everything it created so repeated test runs don't
    pollute the dashboard with TESTUNIT-* rows, and so a second full-suite
    run doesn't pick up this run's leftover units as extra incidents."""
    from sqlalchemy import text as sql_text

    db.execute(sql_text("DELETE FROM incidents WHERE source_type='UNIT_INCIDENT' AND source_id IN "
                         "(SELECT id FROM unit_incidents WHERE storage_unit_id=:u)"), {"u": str(unit_id)})
    db.execute(sql_text("DELETE FROM unit_incidents WHERE storage_unit_id=:u"), {"u": str(unit_id)})
    db.execute(sql_text("DELETE FROM risk_predictions WHERE food_batch_id IN "
                         "(SELECT id FROM food_batches WHERE storage_unit_id=:u)"), {"u": str(unit_id)})
    db.execute(sql_text("DELETE FROM food_batches WHERE storage_unit_id=:u"), {"u": str(unit_id)})
    db.execute(sql_text("DELETE FROM storage_units WHERE id=:u"), {"u": str(unit_id)})
    db.commit()
