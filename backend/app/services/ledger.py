"""
The inventory ledger. This is the single source of truth for "how much of
batch X is left" -- FoodBatch.quantity is only the original delivered
amount; CURRENT quantity is always derived by summing InventoryTransaction
rows (spec section 9, design rule #68: "current inventory must NEVER be
manually typed").
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.food import DataSourceEnum, FoodBatch
from app.models.ledger import InventoryTransaction, TransactionTypeEnum


class LedgerError(Exception):
    """Raised for hard-stop violations: negative stock, using an expired
    batch without an authorized override, etc."""


def current_quantity(db: Session, batch_id) -> float:
    total = db.query(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0)).filter(
        InventoryTransaction.food_batch_id == batch_id
    ).scalar()
    return float(total)


def current_quantities_bulk(db: Session, batch_ids: list) -> dict:
    if not batch_ids:
        return {}
    rows = db.execute(text("""
        SELECT food_batch_id, COALESCE(SUM(quantity_delta), 0)
        FROM inventory_transactions WHERE food_batch_id = ANY(:ids) GROUP BY food_batch_id
    """), {"ids": [str(b) for b in batch_ids]}).fetchall()
    result = {str(bid): 0.0 for bid in batch_ids}
    for bid, total in rows:
        result[str(bid)] = float(total)
    return result


def record_delivery_transaction(
    db: Session, batch: FoodBatch, recorded_by=None, data_source: DataSourceEnum = DataSourceEnum.REAL,
) -> InventoryTransaction:
    """Called once, at batch creation, to seed the ledger with the delivered quantity."""
    txn = InventoryTransaction(
        food_batch_id=batch.id, txn_type=TransactionTypeEnum.DELIVERY,
        quantity_delta=batch.quantity, reason="Initial delivery", reference_type="food_batch",
        reference_id=batch.id, recorded_by=recorded_by, data_source=data_source,
    )
    db.add(txn)
    return txn


def _assert_can_transact(batch: FoodBatch, allow_expired_override: bool, override_reason: str | None) -> None:
    """Hard expiry control (spec section 14): never silently allow expired
    inventory to be consumed. An override requires an explicit reason."""
    if batch.expiry_date < date.today() and not allow_expired_override:
        raise LedgerError(
            f"Batch {batch.batch_code} expired on {batch.expiry_date} — cannot record a normal "
            f"consumption/waste transaction against it. An authorized override with a reason is required."
        )
    if allow_expired_override and not override_reason:
        raise LedgerError("Overriding an expired-batch transaction requires an explicit reason.")
    if batch.is_quarantined and not allow_expired_override:
        raise LedgerError(
            f"Batch {batch.batch_code} is quarantined ({batch.quarantine_reason or 'no reason recorded'}) "
            f"— cannot record a normal transaction against it without an authorized override."
        )


def record_consumption(
    db: Session, batch: FoodBatch, quantity: float, *, meal: str | None = None, department: str | None = None,
    recorded_by=None, data_source: DataSourceEnum = DataSourceEnum.REAL,
    allow_expired_override: bool = False, override_reason: str | None = None,
):
    from app.models.consumption import ConsumptionRecord

    _assert_can_transact(batch, allow_expired_override, override_reason)
    available = current_quantity(db, batch.id)
    if quantity > available:
        raise LedgerError(f"Cannot consume {quantity} — only {available} currently in stock for this batch.")

    record = ConsumptionRecord(
        food_item_id=batch.food_item_id, food_batch_id=batch.id,
        ts=datetime.now(timezone.utc), quantity_consumed=quantity,
        meal=meal, department=department, recorded_by=recorded_by, data_source=data_source,
    )
    db.add(record)
    db.flush()

    txn = InventoryTransaction(
        food_batch_id=batch.id, txn_type=TransactionTypeEnum.CONSUMPTION,
        quantity_delta=-quantity, reason=override_reason or "Consumption",
        reference_type="consumption_record", reference_id=record.id,
        recorded_by=recorded_by, data_source=data_source,
    )
    db.add(txn)
    return record


def record_waste(
    db: Session, batch: FoodBatch, quantity: float, reason: str, *, department: str | None = None,
    notes: str | None = None, recorded_by=None, data_source: DataSourceEnum = DataSourceEnum.REAL,
    allow_expired_override: bool = True,  # wasting an expired batch is normal, not an override case
):
    from app.models.consumption import WastageRecord

    available = current_quantity(db, batch.id)
    if quantity > available:
        raise LedgerError(f"Cannot waste {quantity} — only {available} currently in stock for this batch.")

    from app.database.session import SessionLocal  # noqa: F401  (local import avoids unused warning if refactored)
    unit_price = db.execute(
        text("SELECT unit_price FROM food_items WHERE id=:f"), {"f": str(batch.food_item_id)}
    ).scalar() or 0

    record = WastageRecord(
        food_item_id=batch.food_item_id, food_batch_id=batch.id, ts=datetime.now(timezone.utc),
        quantity_wasted=quantity, reason=reason, department=department, notes=notes,
        estimated_loss=round(float(quantity) * float(unit_price), 2),
        recorded_by=recorded_by, data_source=data_source,
    )
    db.add(record)
    db.flush()

    txn = InventoryTransaction(
        food_batch_id=batch.id, txn_type=TransactionTypeEnum.WASTE,
        quantity_delta=-quantity, reason=reason, reference_type="wastage_record",
        reference_id=record.id, recorded_by=recorded_by, data_source=data_source,
    )
    db.add(txn)
    return record


def record_adjustment(
    db: Session, batch: FoodBatch, delta: float, reason: str, *, recorded_by=None,
    data_source: DataSourceEnum = DataSourceEnum.REAL,
):
    """Stock reconciliation (spec section 30): system vs physical count.
    Always requires a reason -- never silently assume theft or error."""
    if not reason:
        raise LedgerError("Stock adjustments require an explicit reason.")
    if delta < 0 and current_quantity(db, batch.id) + delta < 0:
        raise LedgerError("Adjustment would drive stock negative.")

    txn = InventoryTransaction(
        food_batch_id=batch.id, txn_type=TransactionTypeEnum.ADJUSTMENT,
        quantity_delta=delta, reason=reason, recorded_by=recorded_by, data_source=data_source,
    )
    db.add(txn)
    return txn
