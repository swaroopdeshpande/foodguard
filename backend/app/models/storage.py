import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.food import DataSourceEnum


class StorageUnit(Base):
    __tablename__ = "storage_units"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    unit_type: Mapped[str] = mapped_column(String(30), nullable=False)  # FRIDGE, FREEZER, DRY_STORE
    target_temp_c: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    # explicit configurable safe range -- FoodWise spec #10: "do not hardcode
    # assumptions where hotel-specific policies may differ." Falls back to
    # target_temp_c +/- 2.5 if not set (see storage_rules service).
    min_safe_temp_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    max_safe_temp_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    target_humidity_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    readings: Mapped[list["StorageReading"]] = relationship(back_populates="storage_unit")


class StorageReading(Base):
    __tablename__ = "storage_readings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    temperature_c: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    humidity_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    data_source: Mapped[DataSourceEnum] = mapped_column(
        Enum(DataSourceEnum, name="data_source_enum"), nullable=False, default=DataSourceEnum.REAL, index=True,
    )

    storage_unit: Mapped["StorageUnit"] = relationship(back_populates="readings")
