"""
Label / fraud consistency analysis (post-OCR).

Fully local, rule-based checks against DB history -- deliberately NOT a
black-box ML model, because a fraud/audit finding needs to be explainable
and defensible (see spec section 9 + 25 ethical considerations).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class LabelAnomalyFinding:
    anomaly_type: str
    severity: str
    details: dict


def check_mfg_before_expiry(mfg_date: date, expiry_date: date) -> LabelAnomalyFinding | None:
    if mfg_date >= expiry_date:
        return LabelAnomalyFinding(
            "INCONSISTENT_SHELF_LIFE", "HIGH",
            {"reason": "manufacturing_date is not before expiry_date",
             "manufacturing_date": str(mfg_date), "expiry_date": str(expiry_date)},
        )
    return None


def check_shelf_life_consistency(
    mfg_date: date, expiry_date: date, category_expected_days: int, tolerance_days: int = 3,
) -> LabelAnomalyFinding | None:
    actual_days = (expiry_date - mfg_date).days
    deviation = actual_days - category_expected_days
    if abs(deviation) > tolerance_days:
        return LabelAnomalyFinding(
            "INCONSISTENT_SHELF_LIFE", "MEDIUM" if abs(deviation) <= tolerance_days * 3 else "HIGH",
            {"actual_shelf_life_days": actual_days, "category_expected_days": category_expected_days,
             "deviation_days": deviation},
        )
    return None


def check_duplicate_batch_reuse(
    db: Session, batch_code: str, current_batch_id: str, min_gap_days: int = 20,
) -> LabelAnomalyFinding | None:
    """Same batch code appearing on a delivery far apart in time from another
    -> likely re-stickering / batch-code reuse fraud."""
    rows = db.execute(
        text("""SELECT id, received_at FROM food_batches
                 WHERE batch_code = :code AND id != :cur ORDER BY received_at"""),
        {"code": batch_code, "cur": current_batch_id},
    ).fetchall()
    if not rows:
        return None

    current_received = db.execute(
        text("SELECT received_at FROM food_batches WHERE id = :cur"), {"cur": current_batch_id}
    ).scalar()

    for other_id, other_received in rows:
        gap_days = abs((current_received - other_received).days)
        if gap_days >= min_gap_days:
            return LabelAnomalyFinding(
                "POSSIBLE_BATCH_REUSE", "HIGH",
                {"batch_code": batch_code, "other_batch_id": str(other_id),
                 "gap_days": gap_days, "reason": "same batch code reused after a large time gap"},
            )
    return None


def check_batch_code_already_exists(db: Session, batch_code: str) -> LabelAnomalyFinding | None:
    """Pre-confirm heads-up for a freshly-scanned label (no food_batch row yet):
    does this batch code already exist anywhere in history? Softer than
    check_duplicate_batch_reuse (no gap threshold, no current-batch context)."""
    row = db.execute(
        text("SELECT id, received_at FROM food_batches WHERE batch_code = :code ORDER BY received_at LIMIT 1"),
        {"code": batch_code},
    ).first()
    if not row:
        return None
    return LabelAnomalyFinding(
        "POSSIBLE_BATCH_REUSE", "MEDIUM",
        {"batch_code": batch_code, "existing_batch_id": str(row[0]), "existing_received_at": str(row[1]),
         "reason": "batch code already exists in history; confirm this is a new delivery, not a re-scan"},
    )


def run_all_checks(
    db: Session, batch_id: str, batch_code: str, mfg_date: date, expiry_date: date, category_expected_days: int,
) -> list[LabelAnomalyFinding]:
    findings = []
    for fn, args in [
        (check_mfg_before_expiry, (mfg_date, expiry_date)),
        (check_shelf_life_consistency, (mfg_date, expiry_date, category_expected_days)),
        (check_duplicate_batch_reuse, (db, batch_code, batch_id)),
    ]:
        result = fn(*args)
        if result:
            findings.append(result)
    return findings
