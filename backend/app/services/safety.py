"""
Batch safety status, FEFO recommendation, and the "Can I use this?" /
"Use First" queue logic (spec sections 12, 13, 15, 16).

Deliberately never claims microbiological safety (spec section 55) --
statuses are always phrased as "within configured rules" / "review
required" / "do not use per policy", never "safe to eat".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.ledger import current_quantity

EXPIRING_SOON_DEFAULT_DAYS = 2  # configurable-in-spirit; see note in compute_safety_status


@dataclass
class SafetyResult:
    status: str  # SAFE / EXPIRING_SOON / REVIEW_REQUIRED / DO_NOT_USE / EXPIRED
    reason: str
    can_use: bool


def _had_recent_storage_excursion(db: Session, storage_unit_id, since) -> bool:
    if storage_unit_id is None:
        return False
    row = db.execute(text("""
        SELECT 1 FROM storage_anomalies
        WHERE storage_unit_id = :u AND severity = 'HIGH' AND detected_at >= :since
        LIMIT 1
    """), {"u": str(storage_unit_id), "since": since}).first()
    return row is not None


def compute_safety_status(db: Session, batch_row) -> SafetyResult:
    """batch_row: any object/row with .expiry_date, .is_quarantined,
    .quarantine_reason, .storage_unit_id, .received_at, .status attributes."""
    today = date.today()

    if batch_row.status == "DISCARDED":
        return SafetyResult("EXPIRED", "Batch has been discarded / fully used up.", can_use=False)

    if batch_row.expiry_date < today:
        return SafetyResult("EXPIRED", f"Batch expired on {batch_row.expiry_date} according to configured expiry rules.", can_use=False)

    if batch_row.is_quarantined:
        return SafetyResult(
            "DO_NOT_USE",
            f"Batch is quarantined: {batch_row.quarantine_reason or 'reason not recorded'}. Requires resolution before use.",
            can_use=False,
        )

    if _had_recent_storage_excursion(db, batch_row.storage_unit_id, batch_row.received_at):
        return SafetyResult(
            "REVIEW_REQUIRED",
            "This batch's storage unit had a recorded temperature excursion during its storage window — flagged for inspection before use.",
            can_use=True,  # can be used only after manual review, not hard-blocked like EXPIRED/quarantine
        )

    days_to_expiry = (batch_row.expiry_date - today).days
    if days_to_expiry <= EXPIRING_SOON_DEFAULT_DAYS:
        return SafetyResult(
            "EXPIRING_SOON",
            f"Expires in {days_to_expiry} day(s) — use soon per configured expiry rules.",
            can_use=True,
        )

    return SafetyResult("SAFE", "Within configured rules.", can_use=True)


def can_use_batch(db: Session, batch_id) -> dict:
    row = db.execute(text("""
        SELECT b.id, b.batch_code, b.expiry_date, b.is_quarantined, b.quarantine_reason,
               b.storage_unit_id, b.received_at, b.status, fi.name AS food_item_name
        FROM food_batches b JOIN food_items fi ON fi.id = b.food_item_id
        WHERE b.id = :bid
    """), {"bid": str(batch_id)}).first()
    if not row:
        return {"error": "Batch not found"}

    result = compute_safety_status(db, row)
    qty = current_quantity(db, batch_id)
    return {
        "batch_id": str(row.id), "batch_code": row.batch_code, "food_item_name": row.food_item_name,
        "current_quantity": qty, "expiry_date": str(row.expiry_date),
        "status": result.status, "reason": result.reason, "can_use": result.can_use,
    }


def fefo_recommendation(db: Session, food_item_id) -> list[dict]:
    """Batches for one food item, earliest-expiry-first. First non-zero-qty,
    non-expired, non-quarantined batch is the recommended one to use.

    REAL data only: kitchen staff must never be told to use a synthetic demo
    batch as if it were real inventory (spec design rule #1/#68)."""
    rows = db.execute(text("""
        SELECT b.id, b.batch_code, b.expiry_date, b.is_quarantined, b.quarantine_reason,
               b.storage_unit_id, b.received_at, b.status
        FROM food_batches b
        WHERE b.food_item_id = :fid AND b.status = 'IN_STOCK' AND b.data_source = 'REAL'
        ORDER BY b.expiry_date ASC
    """), {"fid": str(food_item_id)}).fetchall()

    out = []
    recommended_assigned = False
    for r in rows:
        qty = current_quantity(db, r.id)
        if qty <= 0:
            continue
        safety = compute_safety_status(db, r)
        is_recommended = safety.can_use and not recommended_assigned
        if is_recommended:
            recommended_assigned = True
        out.append({
            "batch_id": str(r.id), "batch_code": r.batch_code, "expiry_date": str(r.expiry_date),
            "current_quantity": qty, "status": safety.status, "reason": safety.reason,
            "recommended": is_recommended,
        })
    return out


def check_fefo_violation(db: Session, food_item_id, chosen_batch_id) -> str | None:
    """If the user picks a batch that isn't the earliest-expiring usable one,
    return a warning message (spec section 15); caller decides whether to
    require an override reason."""
    queue = fefo_recommendation(db, food_item_id)
    recommended = next((b for b in queue if b["recommended"]), None)
    if recommended and recommended["batch_id"] != str(chosen_batch_id):
        return (
            f"Batch {recommended['batch_code']} expires earlier ({recommended['expiry_date']}) "
            f"and is recommended for use first."
        )
    return None


def use_first_queue(db: Session, limit: int = 20) -> list[dict]:
    """Global cross-item queue: earliest-expiring usable batches first
    (spec section 16). A lightweight version -- full spec also blends in
    waste prediction, added where a risk_prediction row exists.

    REAL data only -- see fefo_recommendation for why."""
    rows = db.execute(text("""
        SELECT b.id, b.batch_code, b.expiry_date, b.is_quarantined, b.quarantine_reason,
               b.storage_unit_id, b.received_at, b.status, fi.name AS food_item_name
        FROM food_batches b JOIN food_items fi ON fi.id = b.food_item_id
        WHERE b.status = 'IN_STOCK' AND b.expiry_date >= CURRENT_DATE AND b.data_source = 'REAL'
        ORDER BY b.expiry_date ASC
        LIMIT :limit
    """), {"limit": limit * 2}).fetchall()  # over-fetch, some will be zero-qty/unusable

    out = []
    for r in rows:
        qty = current_quantity(db, r.id)
        if qty <= 0:
            continue
        safety = compute_safety_status(db, r)
        if not safety.can_use:
            continue
        latest_risk = db.execute(text("""
            SELECT risk_probability FROM risk_predictions WHERE food_batch_id=:b ORDER BY predicted_at DESC LIMIT 1
        """), {"b": str(r.id)}).scalar()
        out.append({
            "batch_id": str(r.id), "batch_code": r.batch_code, "food_item_name": r.food_item_name,
            "expiry_date": str(r.expiry_date), "current_quantity": qty,
            "status": safety.status, "waste_risk": float(latest_risk) if latest_risk is not None else None,
        })
        if len(out) >= limit:
            break
    return out
