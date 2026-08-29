import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class FoodCategory(Base):
    __tablename__ = "food_categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    perishability_level: Mapped[int] = mapped_column(nullable=False)  # 1 (low) - 5 (very high)
    expected_shelf_life_days: Mapped[int] = mapped_column(nullable=False)
    required_min_temp_c: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    required_max_temp_c: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    items: Mapped[list["FoodItem"]] = relationship(back_populates="category")


class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_categories.id"), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped["FoodCategory"] = relationship(back_populates="items")
    batches: Mapped[list["FoodBatch"]] = relationship(back_populates="food_item")


class FoodBatch(Base):
    __tablename__ = "food_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    storage_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_units.id"), nullable=True, index=True)

    batch_code: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    manufacturing_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_opened: Mapped[bool] = mapped_column(default=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="IN_STOCK")  # IN_STOCK, CONSUMED, DISCARDED, UNDER_REVIEW

    food_item: Mapped["FoodItem"] = relationship(back_populates="batches")
