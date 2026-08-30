import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.food import DataSourceEnum


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    distributor_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    batch_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deliveries: Mapped[list["SupplierDelivery"]] = relationship(back_populates="supplier")


class SupplierDelivery(Base):
    __tablename__ = "supplier_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    food_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("food_batches.id"), nullable=True)

    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    batch_size_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_delay_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    defect_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0)  # 0-1
    rejected_quantity_kg: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    complaint_count: Mapped[int] = mapped_column(default=0)
    price_per_kg: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    remaining_shelf_life_days: Mapped[int] = mapped_column(default=0)
    expiry_margin_days: Mapped[int] = mapped_column(default=0)  # declared shelf life vs category norm

    data_source: Mapped[DataSourceEnum] = mapped_column(
        Enum(DataSourceEnum, name="data_source_enum"), nullable=False, default=DataSourceEnum.REAL, index=True,
    )

    supplier: Mapped["Supplier"] = relationship(back_populates="deliveries")
