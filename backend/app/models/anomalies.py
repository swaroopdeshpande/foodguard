import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class StorageAnomaly(Base):
    """ML Model #2 output: temp/humidity drift & changepoint anomalies."""

    __tablename__ = "storage_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    anomaly_type: Mapped[str] = mapped_column(String(40), nullable=False)  # TEMPERATURE_DRIFT, CUSUM_SHIFT, SPIKE
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # LOW/MEDIUM/HIGH
    current_value: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    expected_value: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    residual: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    trend_per_day: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    estimated_days_to_threshold: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class SupplierAnomaly(Base):
    """ML Model #3 output: Isolation Forest supplier-behaviour anomaly."""

    __tablename__ = "supplier_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    supplier_delivery_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("supplier_deliveries.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    anomaly_score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)  # isolation forest score
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    deviating_features: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)


class ConsumptionAnomaly(Base):
    """Consumption/wastage pattern anomaly (z-score/rolling stats based)."""

    __tablename__ = "consumption_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    z_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    pct_change: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    cross_referenced_food_risk: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    recommendation: Mapped[str] = mapped_column(String(30), default="INVESTIGATE")


class LabelAnomaly(Base):
    """Label/fraud consistency checks: tampering, duplicate batch reuse, shelf-life mismatch."""

    __tablename__ = "label_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    label_scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("label_scans.id"), nullable=False, index=True)
    food_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("food_batches.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    anomaly_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # POSSIBLE_LABEL_TAMPERING / POSSIBLE_BATCH_REUSE / INCONSISTENT_SHELF_LIFE
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class UnitIncident(Base):
    """Correlated multi-item failure attributed to one storage unit."""

    __tablename__ = "unit_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    affected_food_batch_ids: Mapped[dict] = mapped_column(JSONB, default=list)
    correlation_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
