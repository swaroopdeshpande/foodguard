from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.incidents import Incident
from app.schemas.common import IncidentOut

router = APIRouter(prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    db: Session = Depends(get_db),
    department: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 100,
):
    q = db.query(Incident)
    if department:
        q = q.filter(Incident.department == department)
    if severity:
        q = q.filter(Incident.severity == severity)
    if status:
        q = q.filter(Incident.status == status)
    return q.order_by(Incident.created_at.desc()).limit(limit).all()


@router.post("/{incident_id}/resolve", response_model=IncidentOut)
def resolve_incident(incident_id: str, db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(404, detail="Incident not found")
    incident.status = "RESOLVED"
    incident.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)
    return incident
