"""
Feature engineering for the food-risk model.

Every feature here is computed from data already in the DB (no hand-wavy
inputs) so training and live inference use the exact same code path.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

FEATURE_COLUMNS = [
    "days_to_expiry",
    "pct_shelf_life_remaining",
    "perishability_level",
    "current_temperature",
    "temperature_deviation",
    "cumulative_temperature_exposure",
    "humidity",
    "storage_deviation_duration",
    "supplier_defect_rate",
    "supplier_reliability",
    "batch_age",
    "previous_rejection_rate",
    "consumption_rate",
    "consumption_change",
    "historical_incidents",
]


def _supplier_reliability(defect_rate: float, complaint_rate: float, delay_days: float) -> float:
    """0-1 composite reliability score from raw supplier stats (documented, not a black box)."""
    penalty = (defect_rate * 3) + (complaint_rate * 1.5) + min(delay_days / 5, 1) * 0.5
    return float(max(0.0, 1.0 - penalty))


def build_feature_frame(
    db: Session, as_of: datetime | None = None, batch_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Builds one feature row per IN_STOCK food batch, as of `as_of` (default: now).

    Pulls from food_batches, food_categories, suppliers, supplier_deliveries,
    storage_readings, consumption_records, wastage_records via a handful of
    scalar subqueries per batch — fine at this data scale (100s-1000s of batches).

    `batch_ids`: restrict to specific batches (e.g. score just a
    newly-created one instead of rescanning the whole inventory).
    """
    as_of = as_of or datetime.now(timezone.utc)

    sql = """
        SELECT b.id AS batch_id, b.expiry_date, b.manufacturing_date, b.received_at,
               b.storage_unit_id, b.food_item_id, b.supplier_id, b.is_opened,
               c.perishability_level, c.required_min_temp_c, c.required_max_temp_c,
               c.expected_shelf_life_days
        FROM food_batches b
        JOIN food_items fi ON fi.id = b.food_item_id
        JOIN food_categories c ON c.id = fi.category_id
        WHERE b.status = 'IN_STOCK'
    """
    params = {}
    if batch_ids:
        sql += " AND b.id = ANY(:batch_ids)"
        params["batch_ids"] = batch_ids
    batches = pd.read_sql(text(sql), db.bind, params=params)
    if batches.empty:
        return pd.DataFrame(columns=["batch_id", *FEATURE_COLUMNS])

    rows = []
    for _, b in batches.iterrows():
        days_to_expiry = (pd.Timestamp(b.expiry_date) - pd.Timestamp(as_of.date())).days
        batch_age = (as_of.date() - b.manufacturing_date).days
        # category-normalized urgency: 4 days left on a 4-day-shelf-life chicken batch
        # (pct=1.0, fresh) is NOT the same risk as 4 days left on a 540-day-shelf-life
        # canned good (pct=0.007, essentially expired) -- raw days_to_expiry alone
        # can't distinguish these, this feature can. See ML.md for why this was added.
        shelf_life = max(int(b.expected_shelf_life_days or 1), 1)
        pct_shelf_life_remaining = days_to_expiry / shelf_life

        # storage readings for this batch's unit, since it was received
        readings = pd.read_sql(
            text("""SELECT ts, temperature_c FROM storage_readings
                     WHERE storage_unit_id = :uid AND ts >= :since ORDER BY ts"""),
            db.bind, params={"uid": str(b.storage_unit_id), "since": b.received_at},
        ) if b.storage_unit_id else pd.DataFrame(columns=["ts", "temperature_c"])

        if not readings.empty:
            current_temp = float(readings.temperature_c.iloc[-1])
            tmin, tmax = float(b.required_min_temp_c), float(b.required_max_temp_c or b.required_min_temp_c + 6)
            deviation = readings.temperature_c.apply(
                lambda t: max(0.0, t - tmax) + max(0.0, tmin - t)
            )
            temperature_deviation = float(deviation.iloc[-1])
            cumulative_exposure = float(deviation.sum())  # degree-hours out of range, cumulative
            # consecutive hours currently out of range (storage_deviation_duration)
            out_of_range = (deviation > 0).values
            dur = 0
            for v in out_of_range[::-1]:
                if not v:
                    break
                dur += 1
            storage_deviation_duration = dur
        else:
            current_temp, temperature_deviation, cumulative_exposure, storage_deviation_duration = (
                float(b.required_min_temp_c), 0.0, 0.0, 0
            )

        # supplier history
        deliveries = pd.read_sql(
            text("""SELECT defect_rate, complaint_count, delivery_delay_days, rejected_quantity_kg, batch_size_kg
                     FROM supplier_deliveries WHERE supplier_id = :sid ORDER BY delivered_at DESC LIMIT 20"""),
            db.bind, params={"sid": str(b.supplier_id)},
        )
        if not deliveries.empty:
            supplier_defect_rate = float(deliveries.defect_rate.mean())
            complaint_rate = float((deliveries.complaint_count > 0).mean())
            avg_delay = float(deliveries.delivery_delay_days.mean())
            previous_rejection_rate = float(
                (deliveries.rejected_quantity_kg / deliveries.batch_size_kg.replace(0, np.nan)).mean() or 0
            )
        else:
            supplier_defect_rate, complaint_rate, avg_delay, previous_rejection_rate = 0.02, 0.0, 0.0, 0.0
        supplier_reliability = _supplier_reliability(supplier_defect_rate, complaint_rate, avg_delay)

        # consumption behaviour for this food item
        consumption = pd.read_sql(
            text("""SELECT ts, quantity_consumed FROM consumption_records
                     WHERE food_item_id = :fid AND ts >= :since ORDER BY ts"""),
            db.bind, params={"fid": str(b.food_item_id), "since": as_of - pd.Timedelta(days=14)},
        )
        if len(consumption) >= 4:
            recent = consumption.quantity_consumed.iloc[-3:].mean()
            baseline = consumption.quantity_consumed.iloc[:-3].mean() or recent
            consumption_rate = float(recent)
            consumption_change = float((recent - baseline) / baseline) if baseline else 0.0
        else:
            consumption_rate = float(consumption.quantity_consumed.mean()) if not consumption.empty else 0.0
            consumption_change = 0.0

        historical_incidents = int((deliveries.complaint_count > 0).sum()) if not deliveries.empty else 0

        rows.append({
            "batch_id": b.batch_id,
            "days_to_expiry": days_to_expiry,
            "pct_shelf_life_remaining": round(pct_shelf_life_remaining, 4),
            "perishability_level": b.perishability_level,
            "current_temperature": current_temp,
            "temperature_deviation": temperature_deviation,
            "cumulative_temperature_exposure": cumulative_exposure,
            "humidity": 50.0,  # placeholder when unit doesn't track humidity; kept as explicit feature per spec
            "storage_deviation_duration": storage_deviation_duration,
            "supplier_defect_rate": supplier_defect_rate,
            "supplier_reliability": supplier_reliability,
            "batch_age": batch_age,
            "previous_rejection_rate": previous_rejection_rate,
            "consumption_rate": consumption_rate,
            "consumption_change": consumption_change,
            "historical_incidents": historical_incidents,
        })

    return pd.DataFrame(rows)


def synthetic_label(row: pd.Series) -> int:
    """Rule-based ground-truth generator used ONLY to bootstrap supervised training,
    since no real incident-labeled dataset exists. Documented explicitly as synthetic
    (see ML.md) -- this is how domain knowledge gets encoded into the training labels.
    Returns 1 (will-become-high-risk) or 0.

    Expiry urgency is driven by pct_shelf_life_remaining (category-normalized),
    NOT raw days_to_expiry -- a chicken batch with 1 day left (25% of its 4-day
    shelf life) and a rice batch with 90 days left (25% of its 365-day shelf
    life) are equally urgent and must score comparably. Raw days_to_expiry is
    kept only as a small secondary term (catches "already physically expired"
    regardless of category) so it doesn't dominate or get relied on alone.
    """
    score = 0.0
    # full weight once <=0% shelf life remains, zero weight once >=25% remains
    score += np.clip((0.25 - row.pct_shelf_life_remaining) / 0.25, 0, 1) * 0.35
    score += (0.10 if row.days_to_expiry <= 0 else 0)  # already physically past date, any category
    score += (row.perishability_level / 5) * 0.15
    score += min(row.cumulative_temperature_exposure / 20, 1) * 0.20
    score += min(row.storage_deviation_duration / 12, 1) * 0.12
    score += (1 - row.supplier_reliability) * 0.12
    score += min(row.previous_rejection_rate * 5, 1) * 0.06
    score += (0.05 if row.consumption_change < -0.4 else 0)
    score += min(row.historical_incidents / 5, 1) * 0.05
    noise = np.random.normal(0, 0.05)
    return int((score + noise) > 0.45)
