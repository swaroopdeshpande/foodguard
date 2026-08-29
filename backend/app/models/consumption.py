import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    quantity_consumed: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)


class WastageRecord(Base):
    __tablename__ = "wastage_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False, index=True)
    food_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("food_batches.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    quantity_wasted: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(default=None)
    estimated_loss: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
