"""
FoodWise real-data-only endpoints: every write here is tagged data_source=REAL
and goes through the inventory ledger (app/services/ledger.py). This is
distinct from app/api/routes/manual.py, which is FoodGuard's original
anomaly-detection demo entry point (still useful for that feature set, but
doesn't enforce the ledger / FEFO / hard-expiry rules FoodWise requires).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.database.session import get_db
from app.models.food import DataSourceEnum, FoodBatch, FoodItem
from app.models.ledger import InventoryTransaction, TransactionTypeEnum
from app.models.storage import StorageReading
from app.models.suppliers import SupplierDelivery
from app.models.users import RoleEnum
from app.schemas.foodwise import (
    ConsumptionCreate,
    DeliveryCreate,
    DemoControlRequest,
    OccupancyCreate,
    QuarantineCreate,
    StockAdjustmentCreate,
    StorageReadingCreate,
    WasteCreate,
)
from app.services import ledger as ledger_service
from app.services.safety import can_use_batch, check_fefo_violation, fefo_recommendation, use_first_queue

router = APIRouter(prefix="/api/foodwise", tags=["foodwise"], dependencies=[Depends(get_current_user)])

REPO_ROOT = Path(__file__).resolve().parents[4]
GENERATOR = REPO_ROOT / "scripts" / "generate_demo_data.py"
PYTHON = REPO_ROOT / "backend" / "venv" / "bin" / "python"


# ---------------------------------------------------------------- deliveries -> batches

@router.post("/deliveries")
def create_delivery(body: DeliveryCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    food_item_id = body.food_item_id
    if food_item_id is None:
        if not body.new_food_item_name or not body.category_id:
            raise HTTPException(400, detail="Provide food_item_id, or both new_food_item_name and category_id")
        item = FoodItem(
            name=body.new_food_item_name, category_id=body.category_id,
            unit_price=body.unit_cost or 0, unit="kg",
        )
        db.add(item)
        db.flush()
        food_item_id = item.id

    batch = FoodBatch(
        food_item_id=food_item_id, supplier_id=body.supplier_id, storage_unit_id=body.storage_unit_id,
        batch_code=body.batch_code, quantity=body.quantity,
        manufacturing_date=body.manufacturing_date, expiry_date=body.expiry_date,
        status="IN_STOCK", data_source=DataSourceEnum.REAL,
    )
    db.add(batch)
    db.flush()

    ledger_service.record_delivery_transaction(db, batch, recorded_by=user.id, data_source=DataSourceEnum.REAL)

    delivery = SupplierDelivery(
        supplier_id=body.supplier_id, food_batch_id=batch.id, delivered_at=datetime.now(timezone.utc),
        batch_size_kg=body.quantity, price_per_kg=body.unit_cost or 0,
        remaining_shelf_life_days=(body.expiry_date - body.manufacturing_date).days,
        data_source=DataSourceEnum.REAL,
    )
    db.add(delivery)
    db.commit()

    return {
        "batch_id": str(batch.id), "food_item_id": str(food_item_id),
        "batch_code": batch.batch_code, "current_quantity": ledger_service.current_quantity(db, batch.id),
    }


# ---------------------------------------------------------------- consumption

@router.post("/consumption")
def create_consumption(body: ConsumptionCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    batch = db.query(FoodBatch).filter(FoodBatch.id == body.food_batch_id).first()
    if not batch:
        raise HTTPException(404, detail="Batch not found")

    fefo_warning = check_fefo_violation(db, batch.food_item_id, batch.id)

    try:
        record = ledger_service.record_consumption(
            db, batch, body.quantity, meal=body.meal, department=body.department,
            recorded_by=user.id, data_source=DataSourceEnum.REAL,
            allow_expired_override=body.allow_expired_override, override_reason=body.override_reason,
        )
    except ledger_service.LedgerError as e:
        raise HTTPException(400, detail=str(e))

    db.commit()
    return {
        "consumption_id": str(record.id), "remaining_quantity": ledger_service.current_quantity(db, batch.id),
        "fefo_warning": fefo_warning,
    }


# ---------------------------------------------------------------- waste

@router.post("/waste")
def create_waste(body: WasteCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    batch = db.query(FoodBatch).filter(FoodBatch.id == body.food_batch_id).first()
    if not batch:
        raise HTTPException(404, detail="Batch not found")

    try:
        record = ledger_service.record_waste(
            db, batch, body.quantity, body.reason, department=body.department,
            notes=body.notes, recorded_by=user.id, data_source=DataSourceEnum.REAL,
        )
    except ledger_service.LedgerError as e:
        raise HTTPException(400, detail=str(e))

    db.commit()
    return {
        "waste_id": str(record.id), "estimated_loss": float(record.estimated_loss),
        "remaining_quantity": ledger_service.current_quantity(db, batch.id),
    }


# ---------------------------------------------------------------- stock adjustment (reconciliation)

@router.post("/stock-adjustments")
def create_adjustment(body: StockAdjustmentCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    batch = db.query(FoodBatch).filter(FoodBatch.id == body.food_batch_id).first()
    if not batch:
        raise HTTPException(404, detail="Batch not found")
    try:
        ledger_service.record_adjustment(db, batch, body.delta, body.reason, recorded_by=user.id, data_source=DataSourceEnum.REAL)
    except ledger_service.LedgerError as e:
        raise HTTPException(400, detail=str(e))
    db.commit()
    return {"remaining_quantity": ledger_service.current_quantity(db, batch.id)}


# ---------------------------------------------------------------- storage readings

@router.post("/storage-readings")
def create_storage_reading(body: StorageReadingCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    unit = db.execute(text("SELECT id FROM storage_units WHERE id=:u"), {"u": str(body.storage_unit_id)}).first()
    if not unit:
        raise HTTPException(400, detail="storage_unit_id not found")

    reading = StorageReading(
        storage_unit_id=body.storage_unit_id, ts=datetime.now(timezone.utc),
        temperature_c=body.temperature_c, humidity_pct=body.humidity_pct,
        remarks=body.remarks, recorded_by=user.id, data_source=DataSourceEnum.REAL,
    )
    db.add(reading)
    db.commit()

    from app.services.pipeline import run_storage_anomalies
    incidents = run_storage_anomalies(db, unit_id=str(body.storage_unit_id))
    db.commit()

    return {"reading_id": str(reading.id), "anomaly_detected": len(incidents) > 0}


# ---------------------------------------------------------------- occupancy

@router.post("/occupancy")
def create_occupancy(body: OccupancyCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.consumption import OccupancyRecord

    record = OccupancyRecord(
        record_date=body.record_date, occupancy_pct=body.occupancy_pct,
        expected_guests=body.expected_guests, actual_guests=body.actual_guests,
        event_type=body.event_type, notes=body.notes, recorded_by=user.id,
        data_source=DataSourceEnum.REAL,
    )
    db.add(record)
    db.commit()
    return {"occupancy_id": str(record.id)}


# ---------------------------------------------------------------- quarantine

@router.post("/batches/{batch_id}/quarantine")
def quarantine_batch(batch_id: str, body: QuarantineCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    batch = db.query(FoodBatch).filter(FoodBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, detail="Batch not found")
    batch.is_quarantined = True
    batch.quarantine_reason = body.reason
    db.commit()
    return {"batch_id": batch_id, "is_quarantined": True, "reason": body.reason}


@router.post("/batches/{batch_id}/release")
def release_batch(batch_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    batch = db.query(FoodBatch).filter(FoodBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, detail="Batch not found")
    batch.is_quarantined = False
    batch.quarantine_reason = None
    db.commit()
    return {"batch_id": batch_id, "is_quarantined": False}


# ---------------------------------------------------------------- safety / FEFO / use-first

@router.get("/batches/{batch_id}/can-use")
def get_can_use(batch_id: str, db: Session = Depends(get_db)):
    result = can_use_batch(db, batch_id)
    if "error" in result:
        raise HTTPException(404, detail=result["error"])
    return result


@router.get("/fefo/{food_item_id}")
def get_fefo(food_item_id: str, db: Session = Depends(get_db)):
    return fefo_recommendation(db, food_item_id)


@router.get("/use-first")
def get_use_first(limit: int = 20, db: Session = Depends(get_db)):
    return use_first_queue(db, limit)


# ---------------------------------------------------------------- dashboard (REAL data only, dynamic)

@router.get("/dashboard")
def foodwise_dashboard(db: Session = Depends(get_db)):
    """Every number here comes from data_source='REAL' rows only. If the hotel
    hasn't entered anything yet, this returns honest zeros/empty-state flags
    -- never synthetic filler (spec sections 1, 45, 68)."""
    real_batches = db.execute(text(
        "SELECT count(*) FROM food_batches WHERE data_source='REAL' AND status='IN_STOCK'"
    )).scalar() or 0

    if real_batches == 0:
        return {
            "has_real_data": False,
            "message": "No real inventory data yet. Add your first delivery to begin.",
        }

    batch_rows = db.execute(text("""
        SELECT b.id, b.expiry_date, fi.unit_price
        FROM food_batches b JOIN food_items fi ON fi.id=b.food_item_id
        WHERE b.data_source='REAL' AND b.status='IN_STOCK'
    """)).fetchall()

    total_value = 0.0
    expiring_soon = 0
    expired = 0
    from datetime import date as date_cls
    today = date_cls.today()
    for bid, expiry, price in batch_rows:
        qty = ledger_service.current_quantity(db, bid)
        total_value += qty * float(price or 0)
        days_left = (expiry - today).days
        if days_left < 0:
            expired += 1
        elif days_left <= 2:
            expiring_soon += 1

    today_consumption = db.execute(text("""
        SELECT COALESCE(SUM(quantity_consumed),0) FROM consumption_records
        WHERE data_source='REAL' AND ts::date = CURRENT_DATE
    """)).scalar() or 0
    today_waste_qty = db.execute(text("""
        SELECT COALESCE(SUM(quantity_wasted),0) FROM wastage_records
        WHERE data_source='REAL' AND ts::date = CURRENT_DATE
    """)).scalar() or 0
    today_waste_cost = db.execute(text("""
        SELECT COALESCE(SUM(estimated_loss),0) FROM wastage_records
        WHERE data_source='REAL' AND ts::date = CURRENT_DATE
    """)).scalar() or 0
    quarantined = db.execute(text(
        "SELECT count(*) FROM food_batches WHERE data_source='REAL' AND is_quarantined=true"
    )).scalar() or 0

    return {
        "has_real_data": True,
        "real_batches_in_stock": real_batches,
        "inventory_value": round(total_value, 2),
        "expiring_soon_batches": expiring_soon,
        "expired_batches": expired,
        "quarantined_batches": quarantined,
        "today_consumption_qty": float(today_consumption),
        "today_waste_qty": float(today_waste_qty),
        "today_waste_cost": float(today_waste_cost),
    }


# ---------------------------------------------------------------- demo data controls (spec section 2)

@router.post("/demo/load", dependencies=[Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER))])
def load_demo_data(body: DemoControlRequest):
    """Runs the synthetic generator. WARNING: the generator currently resets
    the ENTIRE schema (all REAL data included) -- see docs/OFFLINE_CHECK.md
    style honesty note in README. A future improvement is a demo-only-reset
    mode that preserves REAL rows; not built in this pass."""
    proc = subprocess.run(
        [str(PYTHON), str(GENERATOR), "--scenario", body.scenario, "--days", str(body.days)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise HTTPException(500, detail=proc.stderr[-2000:])
    return {"status": "demo data loaded", "scenario": body.scenario, "warning": "This reset ALL data, including any real records entered so far."}


@router.post("/demo/clear", dependencies=[Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER))])
def clear_demo_data(db: Session = Depends(get_db)):
    """Deletes data_source='DEMO' rows from every source-of-truth table,
    leaving REAL data intact. ML-derived output tables (incidents,
    risk_predictions, anomaly tables) have no data_source column of their
    own -- they're wiped unconditionally here since they're regenerated by
    the next pipeline run anyway, not source-of-truth records."""
    deleted = {}
    for table in ["incidents", "risk_predictions", "storage_anomalies",
                  "supplier_anomalies", "consumption_anomalies", "label_anomalies", "unit_incidents"]:
        result = db.execute(text(f"DELETE FROM {table}"))
        deleted[table] = result.rowcount

    for table in ["inventory_transactions", "consumption_records", "wastage_records",
                  "storage_readings", "supplier_deliveries", "occupancy_records", "food_batches"]:
        result = db.execute(text(f"DELETE FROM {table} WHERE data_source='DEMO'"))
        deleted[table] = result.rowcount

    db.commit()
    return {"status": "demo data cleared", "deleted": deleted}
