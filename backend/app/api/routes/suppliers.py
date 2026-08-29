from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.schemas.common import SupplierOut

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT s.id, s.name, a.anomaly_score, a.severity, a.deviating_features
        FROM suppliers s
        LEFT JOIN LATERAL (
            SELECT anomaly_score, severity, deviating_features FROM supplier_anomalies sa
            WHERE sa.supplier_id = s.id ORDER BY detected_at DESC LIMIT 1
        ) a ON true
        ORDER BY s.name
    """)).mappings().fetchall()

    return [
        SupplierOut(
            id=r["id"], name=r["name"],
            latest_anomaly_score=float(r["anomaly_score"]) if r["anomaly_score"] is not None else None,
            latest_severity=r["severity"], deviating_features=r["deviating_features"],
        )
        for r in rows
    ]
