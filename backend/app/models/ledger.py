import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.food import DataSourceEnum


class TransactionTypeEnum(str, enum.Enum):
    DELIVERY = "DELIVERY"          # +quantity, created automatically when a batch is received
    CONSUMPTION = "CONSUMPTION"    # -quantity
    WASTE = "WASTE"                # -quantity
    ADJUSTMENT = "ADJUSTMENT"      # +/- quantity, requires a reason (stock reconciliation, spec #30)
    TRANSFER = "TRANSFER"          # +/- quantity, moving stock between storage units (net zero across a pair)


class InventoryTransaction(Base):
    """The ledger. Every stock movement is a row here; a batch's CURRENT
    quantity is ALWAYS derived by summing this table, never read from a
    manually-typed field (spec section 9 / design rule #68). FoodBatch.quantity
    holds only the original delivered amount for reference.
    """

    __tablename__ = "inventory_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_batches.id"), nullable=False, index=True)
    txn_type: Mapped[TransactionTypeEnum] = mapped_column(
        Enum(TransactionTypeEnum, name="transaction_type_enum"), nullable=False,
    )
    quantity_delta: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # signed: DELIVERY/ADJUSTMENT(+) positive, CONSUMPTION/WASTE/ADJUSTMENT(-) negative

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)  # e.g. "consumption_record", "wastage_record"
    reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    data_source: Mapped[DataSourceEnum] = mapped_column(
        Enum(DataSourceEnum, name="data_source_enum"), nullable=False, default=DataSourceEnum.REAL, index=True,
    )
