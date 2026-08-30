import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.food import DataSourceEnum


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False, index=True)
    food_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("food_batches.id"), nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    quantity_consumed: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    meal: Mapped[str | None] = mapped_column(String(30), nullable=True)  # BREAKFAST/LUNCH/DINNER/EVENT
    department: Mapped[str | None] = mapped_column(String(60), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    data_source: Mapped[DataSourceEnum] = mapped_column(
        Enum(DataSourceEnum, name="data_source_enum"), nullable=False, default=DataSourceEnum.REAL, index=True,
    )


class WastageRecord(Base):
    __tablename__ = "wastage_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False, index=True)
    food_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("food_batches.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    quantity_wasted: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(default=None)
    # EXPIRED/SPOILAGE/OVERPRODUCTION/DAMAGED/STORAGE_ISSUE/PREPARATION_WASTE/
    # BUFFET_LEFTOVER/QUALITY_REJECTION/OTHER (spec section 21)
    department: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estimated_loss: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    data_source: Mapped[DataSourceEnum] = mapped_column(
        Enum(DataSourceEnum, name="data_source_enum"), nullable=False, default=DataSourceEnum.REAL, index=True,
    )


class OccupancyRecord(Base):
    """Hotel occupancy / covers / event data -- forecasting features
    (spec section 22)."""

    __tablename__ = "occupancy_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    record_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    occupancy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    expected_guests: Mapped[int | None] = mapped_column(nullable=True)
    actual_guests: Mapped[int | None] = mapped_column(nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(60), nullable=True)  # NONE/BANQUET/WEDDING/CONFERENCE
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    data_source: Mapped[DataSourceEnum] = mapped_column(
        Enum(DataSourceEnum, name="data_source_enum"), nullable=False, default=DataSourceEnum.REAL, index=True,
    )
