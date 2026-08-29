"""
Manual data entry: type in a batch/reading/delivery/consumption record
yourself and get the actual model/anomaly output for exactly what you
entered, immediately -- not a bulk scenario regeneration.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.anomalies import ConsumptionAnomaly, StorageAnomaly, SupplierAnomaly
from app.models.consumption import ConsumptionRecord
from app.models.food import FoodBatch, FoodItem
from app.models.incidents import Incident
from app.models.risk import RiskPrediction
from app.models.storage import StorageReading
from app.models.suppliers import SupplierDelivery
from app.schemas.manual import (
    CategoryRef,
    FoodItemRef,
    ManualBatchCreate,
    ManualConsumptionCreate,
    ManualDeliveryCreate,
    ManualEntryResult,
    ManualReadingCreate,
    StorageUnitRef,
)
from app.services.pipeline import (
    run_consumption_anomalies,
    run_food_risk,
    run_storage_anomalies,
    run_supplier_anomalies,
)

router = APIRouter(prefix="/api/manual", tags=["manual-entry"], dependencies=[Depends(get_current_user)])


def _incident_dict(inc: Incident | None) -> dict | None:
    if inc is None:
        return None
    return {
        "action": inc.action.value if hasattr(inc.action, "value") else inc.action,
        "department": inc.department.value if hasattr(inc.department, "value") else inc.department,
        "severity": inc.severity,
        "reason_codes": inc.reason_codes,
        "dimensions_snapshot": inc.dimensions_snapshot,
    }


async def _broadcast_refresh():
    """Push a lightweight event so every connected dashboard refetches,
    same mechanism the scenario-trigger live-sim uses."""
    from app.services.simulation import manager
    await manager.broadcast({"type": "MANUAL_ENTRY", "message": "New data submitted"})


# ---------------------------------------------------------------- reference data

@router.get("/reference/categories", response_model=list[CategoryRef])
def list_categories(db: Session = Depends(get_db)):
    rows = db.execute(text(
        "SELECT id, name, required_min_temp_c, required_max_temp_c, expected_shelf_life_days FROM food_categories ORDER BY name"
    )).mappings().fetchall()
    return [CategoryRef(**r) for r in rows]


@router.get("/reference/food-items", response_model=list[FoodItemRef])
def list_food_items(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT fi.id, fi.name, fi.category_id, c.name AS category_name
        FROM food_items fi JOIN food_categories c ON c.id = fi.category_id ORDER BY fi.name
    """)).mappings().fetchall()
    return [FoodItemRef(**r) for r in rows]


@router.get("/reference/suppliers")
def list_suppliers_ref(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, name FROM suppliers ORDER BY name")).mappings().fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


@router.get("/reference/storage-units", response_model=list[StorageUnitRef])
def list_storage_units_ref(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, name, target_temp_c FROM storage_units ORDER BY name")).mappings().fetchall()
    return [StorageUnitRef(**r) for r in rows]


# ---------------------------------------------------------------- create + score

@router.post("/batches", response_model=ManualEntryResult)
async def create_batch(body: ManualBatchCreate, db: Session = Depends(get_db)):
    food_item_id = body.food_item_id
    if food_item_id is None:
        if not body.new_food_item_name or not body.category_id:
            raise HTTPException(400, detail="Provide food_item_id, or both new_food_item_name and category_id")
        cat_price_row = db.execute(text("SELECT 1 FROM food_categories WHERE id=:c"), {"c": str(body.category_id)}).first()
        if not cat_price_row:
            raise HTTPException(400, detail="category_id not found")
        item = FoodItem(name=body.new_food_item_name, category_id=body.category_id, unit_price=0, unit="kg")
        db.add(item)
        db.flush()
        food_item_id = item.id

    batch = FoodBatch(
        food_item_id=food_item_id, supplier_id=body.supplier_id, storage_unit_id=body.storage_unit_id,
        batch_code=body.batch_code, quantity=body.quantity,
        manufacturing_date=body.manufacturing_date, expiry_date=body.expiry_date,
        status="IN_STOCK",
    )
    db.add(batch)
    db.commit()  # must commit before scoring: build_feature_frame's pd.read_sql opens a
                 # separate raw connection off db.bind that can't see flushed-but-uncommitted rows

    incidents = run_food_risk(db, batch_ids=[str(batch.id)])
    db.commit()

    rp = db.query(RiskPrediction).filter(RiskPrediction.food_batch_id == batch.id).order_by(
        RiskPrediction.predicted_at.desc()
    ).first()

    await _broadcast_refresh()

    return ManualEntryResult(
        created_id=batch.id,
        risk_prediction={
            "risk_probability": float(rp.risk_probability), "risk_class": rp.risk_class,
            "top_factors": rp.top_factors,
        } if rp else None,
        incident=_incident_dict(incidents[0] if incidents else None),
    )


@router.post("/storage-readings", response_model=ManualEntryResult)
async def create_reading(body: ManualReadingCreate, db: Session = Depends(get_db)):
    unit = db.execute(text("SELECT id FROM storage_units WHERE id=:u"), {"u": str(body.storage_unit_id)}).first()
    if not unit:
        raise HTTPException(400, detail="storage_unit_id not found")

    reading = StorageReading(
        storage_unit_id=body.storage_unit_id, ts=datetime.now(timezone.utc),
        temperature_c=body.temperature_c, humidity_pct=body.humidity_pct,
    )
    db.add(reading)
    db.commit()  # commit before scoring -- see note in create_batch

    incidents = run_storage_anomalies(db, unit_id=str(body.storage_unit_id))
    db.commit()

    anomaly = db.query(StorageAnomaly).filter(StorageAnomaly.storage_unit_id == body.storage_unit_id).order_by(
        StorageAnomaly.detected_at.desc()
    ).first()

    await _broadcast_refresh()

    return ManualEntryResult(
        created_id=reading.id,
        storage_anomaly={
            "anomaly_type": anomaly.anomaly_type, "severity": anomaly.severity,
            "current_value": float(anomaly.current_value), "expected_value": float(anomaly.expected_value),
            "estimated_days_to_threshold": float(anomaly.estimated_days_to_threshold) if anomaly.estimated_days_to_threshold is not None else None,
        } if anomaly and incidents else None,
        incident=_incident_dict(incidents[0] if incidents else None),
    )


@router.post("/supplier-deliveries", response_model=ManualEntryResult)
async def create_delivery(body: ManualDeliveryCreate, db: Session = Depends(get_db)):
    supplier = db.execute(text("SELECT id FROM suppliers WHERE id=:s"), {"s": str(body.supplier_id)}).first()
    if not supplier:
        raise HTTPException(400, detail="supplier_id not found")

    delivery = SupplierDelivery(
        supplier_id=body.supplier_id, delivered_at=datetime.now(timezone.utc),
        batch_size_kg=body.batch_size_kg, delivery_delay_days=body.delivery_delay_days,
        defect_rate=body.defect_rate, rejected_quantity_kg=body.rejected_quantity_kg,
        complaint_count=body.complaint_count, price_per_kg=body.price_per_kg,
        remaining_shelf_life_days=body.remaining_shelf_life_days, expiry_margin_days=body.expiry_margin_days,
    )
    db.add(delivery)
    db.commit()  # commit before scoring -- see note in create_batch

    incidents = run_supplier_anomalies(db, supplier_id=str(body.supplier_id))
    db.commit()

    anomaly = db.query(SupplierAnomaly).filter(SupplierAnomaly.supplier_id == body.supplier_id).order_by(
        SupplierAnomaly.detected_at.desc()
    ).first()

    await _broadcast_refresh()

    return ManualEntryResult(
        created_id=delivery.id,
        supplier_anomaly={
            "anomaly_score": float(anomaly.anomaly_score), "severity": anomaly.severity,
            "deviating_features": anomaly.deviating_features,
        } if anomaly and incidents else None,
        incident=_incident_dict(incidents[0] if incidents else None),
    )


@router.post("/consumption", response_model=ManualEntryResult)
async def create_consumption(body: ManualConsumptionCreate, db: Session = Depends(get_db)):
    item = db.execute(text("SELECT id FROM food_items WHERE id=:f"), {"f": str(body.food_item_id)}).first()
    if not item:
        raise HTTPException(400, detail="food_item_id not found")

    record = ConsumptionRecord(
        food_item_id=body.food_item_id, ts=datetime.now(timezone.utc),
        quantity_consumed=body.quantity_consumed,
    )
    db.add(record)
    db.commit()  # commit before scoring -- see note in create_batch

    incidents = run_consumption_anomalies(db, food_item_id=str(body.food_item_id))
    db.commit()

    anomaly = db.query(ConsumptionAnomaly).filter(ConsumptionAnomaly.food_item_id == body.food_item_id).order_by(
        ConsumptionAnomaly.detected_at.desc()
    ).first()

    await _broadcast_refresh()

    return ManualEntryResult(
        created_id=record.id,
        consumption_anomaly={
            "z_score": float(anomaly.z_score), "pct_change": float(anomaly.pct_change),
            "severity": anomaly.severity, "recommendation": anomaly.recommendation,
        } if anomaly and incidents else None,
        incident=_incident_dict(incidents[0] if incidents else None),
    )
