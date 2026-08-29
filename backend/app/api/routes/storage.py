from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.schemas.common import StorageUnitOut

router = APIRouter(prefix="/api/storage", tags=["storage"], dependencies=[Depends(get_current_user)])


@router.get("/units", response_model=list[StorageUnitOut])
def list_units(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT su.id, su.name, su.unit_type, su.target_temp_c,
               latest_reading.temperature_c,
               anomaly.anomaly_type, anomaly.severity, anomaly.estimated_days_to_threshold
        FROM storage_units su
        LEFT JOIN LATERAL (
            SELECT temperature_c FROM storage_readings sr
            WHERE sr.storage_unit_id = su.id ORDER BY ts DESC LIMIT 1
        ) latest_reading ON true
        LEFT JOIN LATERAL (
            SELECT anomaly_type, severity, estimated_days_to_threshold FROM storage_anomalies sa
            WHERE sa.storage_unit_id = su.id ORDER BY detected_at DESC LIMIT 1
        ) anomaly ON true
        ORDER BY su.name
    """)).mappings().fetchall()

    return [
        StorageUnitOut(
            id=r["id"], name=r["name"], unit_type=r["unit_type"], target_temp_c=float(r["target_temp_c"]),
            current_temperature=float(r["temperature_c"]) if r["temperature_c"] is not None else None,
            latest_anomaly_type=r["anomaly_type"], latest_severity=r["severity"],
            estimated_days_to_threshold=float(r["estimated_days_to_threshold"]) if r["estimated_days_to_threshold"] is not None else None,
        )
        for r in rows
    ]
