import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    action: Mapped[str] = mapped_column(String(120), nullable=False)
    object_type: Mapped[str] = mapped_column(String(60), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    previous_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(60), nullable=False)  # food_risk/supplier_anomaly/storage_forecaster
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    training_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    feature_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_path: Mapped[str] = mapped_column(String(500), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), default="synthetic-v1")
    is_active: Mapped[bool] = mapped_column(default=True)
