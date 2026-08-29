import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ActionEnum(str, enum.Enum):
    SAFE = "SAFE"
    MONITOR = "MONITOR"
    CHECK = "CHECK"
    PRIORITY_CHECK = "PRIORITY_CHECK"
    DO_NOT_SERVE = "DO_NOT_SERVE"
    MAINTENANCE_ALERT = "MAINTENANCE_ALERT"
    SUPPLIER_REVIEW = "SUPPLIER_REVIEW"
    FRAUD_REVIEW = "FRAUD_REVIEW"
    INVESTIGATE = "INVESTIGATE"


class DepartmentEnum(str, enum.Enum):
    KITCHEN = "KITCHEN"
    MAINTENANCE = "MAINTENANCE"
    PROCUREMENT = "PROCUREMENT"
    AUDIT = "AUDIT"
    INVESTIGATION = "INVESTIGATION"


class Incident(Base):
    """Fusion-engine output: a single actionable incident routed to a department."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # FOOD_RISK / STORAGE_ANOMALY / SUPPLIER_ANOMALY / LABEL_ANOMALY / UNIT_INCIDENT / CONSUMPTION_ANOMALY
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    action: Mapped[ActionEnum] = mapped_column(Enum(ActionEnum, name="action_enum"), nullable=False)
    department: Mapped[DepartmentEnum] = mapped_column(Enum(DepartmentEnum, name="department_enum"), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN/ACKNOWLEDGED/RESOLVED

    reason_codes: Mapped[dict] = mapped_column(JSONB, default=list)
    dimensions_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    # e.g. {"food_risk":0.82,"storage_anomaly":"HIGH","supplier_anomaly":"LOW", ...}
