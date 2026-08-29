from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.schemas.common import DashboardSummary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db)):
    total_batches = db.execute(text("SELECT count(*) FROM food_batches WHERE status='IN_STOCK'")).scalar()

    high_risk = db.execute(text("""
        SELECT count(DISTINCT rp.food_batch_id) FROM risk_predictions rp
        WHERE rp.risk_class = 'HIGH' AND rp.predicted_at = (
            SELECT max(predicted_at) FROM risk_predictions rp2 WHERE rp2.food_batch_id = rp.food_batch_id
        )
    """)).scalar()

    open_incidents = db.execute(text("SELECT count(*) FROM incidents WHERE status='OPEN'")).scalar()

    by_department = dict(db.execute(text(
        "SELECT department, count(*) FROM incidents WHERE status='OPEN' GROUP BY department"
    )).fetchall())
    by_action = dict(db.execute(text(
        "SELECT action, count(*) FROM incidents WHERE status='OPEN' GROUP BY action"
    )).fetchall())

    wastage_loss = db.execute(text("SELECT COALESCE(sum(estimated_loss), 0) FROM wastage_records")).scalar()

    active_storage = db.execute(text(
        "SELECT count(*) FROM storage_anomalies WHERE detected_at > now() - interval '1 day'"
    )).scalar()
    active_supplier = db.execute(text(
        "SELECT count(*) FROM supplier_anomalies WHERE detected_at > now() - interval '7 days'"
    )).scalar()

    return DashboardSummary(
        total_batches_in_stock=total_batches or 0,
        high_risk_batches=high_risk or 0,
        open_incidents=open_incidents or 0,
        incidents_by_department={str(k): v for k, v in by_department.items()},
        incidents_by_action={str(k): v for k, v in by_action.items()},
        estimated_wastage_loss=float(wastage_loss or 0),
        active_storage_anomalies=active_storage or 0,
        active_supplier_anomalies=active_supplier or 0,
    )
