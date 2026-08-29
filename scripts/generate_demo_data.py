"""
FoodGuard synthetic data generator.

DATA_SOURCE = SYNTHETIC. No real hotel/restaurant data is used or claimed.
This generator encodes domain-realistic relationships (see README section below)
so that the ML models have genuine signal to learn from, instead of random noise.

Usage:
    python scripts/generate_demo_data.py --scenario normal
    python scripts/generate_demo_data.py --scenario fridge_drift
    python scripts/generate_demo_data.py --scenario supplier_anomaly
    python scripts/generate_demo_data.py --scenario unit_failure
    python scripts/generate_demo_data.py --scenario label_fraud
    python scripts/generate_demo_data.py --scenario consumption_drop
    python scripts/generate_demo_data.py --scenario all --days 180

Domain relationships encoded (see PROJECT ML.md for detail):
    closer expiry              -> higher risk
    higher cumulative temp exp -> higher risk
    highly perishable food     -> faster deterioration curve
    poor supplier history      -> increased risk
    long storage deviation     -> increased risk
"""
from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.models.consumption import ConsumptionRecord, WastageRecord  # noqa: E402
from app.models.food import FoodBatch, FoodCategory, FoodItem  # noqa: E402
from app.models.storage import StorageReading, StorageUnit  # noqa: E402
from app.models.suppliers import Supplier, SupplierDelivery  # noqa: E402
from app.models.users import RoleEnum, User  # noqa: E402

RNG = random.Random(42)  # fixed seed -> reproducible demo runs

CATEGORY_DEFS = [
    # name, perishability(1-5), shelf_life_days, min_temp, max_temp
    ("Chicken",       5, 4,   0.0, 4.0),
    ("Fish/Seafood",  5, 2,  -2.0, 2.0),
    ("Milk",          4, 7,   2.0, 5.0),
    ("Paneer",        4, 5,   2.0, 5.0),
    ("Yogurt",        4, 10,  2.0, 5.0),
    ("Leafy Greens",  4, 5,   2.0, 6.0),
    ("Eggs",          3, 21,  2.0, 7.0),
    ("Bread",         3, 5,  18.0, 25.0),
    ("Rice",          1, 365, 15.0, 28.0),
    ("Canned Goods",  1, 540, 15.0, 28.0),
]

SUPPLIER_NAMES = [
    "GreenValley Farms", "CoastalCatch Seafood", "DailyDairy Co",
    "FreshLeaf Produce", "GrainWorks Wholesale", "SunnyPoultry Ltd",
    "MetroCold Storage Supply", "Harvest Direct",
]

STORAGE_UNIT_DEFS = [
    ("FRIDGE_01", "FRIDGE", 4.0, 55.0),
    ("FRIDGE_02", "FRIDGE", 4.0, 55.0),
    ("FRIDGE_03", "FRIDGE", 4.0, 55.0),
    ("FREEZER_01", "FREEZER", -18.0, None),
    ("DRYSTORE_01", "DRY_STORE", 22.0, 45.0),
]


def reset_schema():
    """Drop and recreate all tables for a clean demo run."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_reference_data(db: Session):
    categories = {}
    for name, perish, shelf, tmin, tmax in CATEGORY_DEFS:
        c = FoodCategory(
            name=name, perishability_level=perish,
            expected_shelf_life_days=shelf,
            required_min_temp_c=tmin, required_max_temp_c=tmax,
        )
        db.add(c)
        categories[name] = c

    suppliers = {}
    for i, name in enumerate(SUPPLIER_NAMES):
        s = Supplier(
            name=name,
            contact_email=f"orders@{name.lower().replace(' ', '')}.example",
            warehouse_id=f"WH-{(i % 3) + 1}",       # deliberately share warehouses -> graph analysis hook
            distributor_id=f"DIST-{(i % 4) + 1}",
            batch_prefix=f"{name[:3].upper()}",
        )
        db.add(s)
        suppliers[name] = s

    units = {}
    for name, utype, target_temp, target_hum in STORAGE_UNIT_DEFS:
        u = StorageUnit(name=name, unit_type=utype, target_temp_c=target_temp, target_humidity_pct=target_hum)
        db.add(u)
        units[name] = u

    # Demo accounts recreated on every reset (scenario triggers drop/recreate
    # all tables including `users`) -- always-known credentials so the demo
    # never gets locked out of its own dashboard. NOT for production use.
    for email, name, role in [
        ("admin@foodguard.internal", "Admin User", RoleEnum.ADMIN),
        ("manager@foodguard.internal", "Demo Manager", RoleEnum.MANAGER),
        ("kitchen@foodguard.internal", "Kitchen Staff", RoleEnum.KITCHEN),
    ]:
        db.add(User(email=email, full_name=name, hashed_password=hash_password("demo1234"), role=role))

    db.flush()
    return categories, suppliers, units


def category_food_items(db: Session, categories: dict[str, FoodCategory]) -> dict[str, FoodItem]:
    items = {}
    price_map = {
        "Chicken": 260, "Fish/Seafood": 550, "Milk": 62, "Paneer": 380,
        "Yogurt": 90, "Leafy Greens": 45, "Eggs": 6.5, "Bread": 45,
        "Rice": 70, "Canned Goods": 120,
    }
    for name, cat in categories.items():
        item = FoodItem(name=name, category_id=cat.id, unit_price=price_map[name], unit="kg")
        db.add(item)
        items[name] = item
    db.flush()
    return items


def assign_storage_for_category(cat_name: str, units: dict[str, StorageUnit]) -> StorageUnit:
    if cat_name in ("Rice", "Canned Goods", "Bread"):
        return units["DRYSTORE_01"]
    if cat_name == "Fish/Seafood":
        return units["FREEZER_01"]
    return RNG.choice([units["FRIDGE_01"], units["FRIDGE_02"], units["FRIDGE_03"]])


@dataclass
class SupplierProfile:
    base_defect_rate: float
    base_delay_days: float
    base_batch_kg: float
    reliability: float  # 0-1, higher = better


def build_supplier_profiles(suppliers: dict[str, Supplier]) -> dict[str, SupplierProfile]:
    profiles = {}
    for name in suppliers:
        reliability = RNG.uniform(0.6, 0.97)
        profiles[name] = SupplierProfile(
            base_defect_rate=round((1 - reliability) * 0.12, 4),
            base_delay_days=round((1 - reliability) * 3, 2),
            base_batch_kg=RNG.uniform(60, 150),
            reliability=reliability,
        )
    return profiles


def generate_storage_readings(db: Session, units: dict[str, StorageUnit], days: int, scenario: str):
    """Hourly readings per unit. Encodes: normal = tight noise around target.
    fridge_drift scenario injects a slow linear drift + noise on FRIDGE_03 over the last 8 days."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    for uname, unit in units.items():
        target = float(unit.target_temp_c)
        n_hours = days * 24
        for h in range(n_hours):
            ts = start + timedelta(hours=h)
            noise = RNG.gauss(0, 0.25 if unit.unit_type != "DRY_STORE" else 0.8)
            temp = target + noise

            if scenario == "fridge_drift" and uname == "FRIDGE_03":
                drift_start_hour = n_hours - (8 * 24)
                if h >= drift_start_hour:
                    days_into_drift = (h - drift_start_hour) / 24
                    temp += 0.38 * days_into_drift  # ~0.38C/day drift, matches spec example

            if scenario == "unit_failure" and uname == "FRIDGE_02":
                failure_start_hour = n_hours - (3 * 24)
                if h >= failure_start_hour:
                    temp += 3.5  # sudden compressor-style failure, affects everything stored there

            db.add(StorageReading(
                storage_unit_id=unit.id, ts=ts,
                temperature_c=round(temp, 2),
                humidity_pct=round(RNG.uniform(40, 65), 1) if unit.target_humidity_pct else None,
            ))
        db.flush()


def generate_supplier_deliveries_and_batches(
    db: Session, suppliers: dict[str, Supplier], profiles: dict[str, SupplierProfile],
    categories: dict[str, FoodCategory], items: dict[str, FoodItem], units: dict[str, StorageUnit],
    days: int, scenario: str,
) -> list[FoodBatch]:
    now = datetime.now(timezone.utc)
    batches: list[FoodBatch] = []
    supplier_names = list(suppliers.keys())
    anomalous_supplier = supplier_names[1]  # "CoastalCatch Seafood" gets the injected anomaly
    reused_batch_code = None

    delivery_interval_days = 3
    n_deliveries = days // delivery_interval_days

    for d in range(n_deliveries):
        delivered_at = now - timedelta(days=days - d * delivery_interval_days)
        is_recent = d >= n_deliveries - 4  # last few deliveries = "current" window for anomaly injection

        for sname in supplier_names:
            supplier = suppliers[sname]
            profile = profiles[sname]
            # each supplier tends to specialize in 1-2 categories (more realistic than uniform random)
            cat_choices = list(categories.keys())
            cat_name = cat_choices[hash(sname) % len(cat_choices)] if RNG.random() < 0.6 else RNG.choice(cat_choices)
            category = categories[cat_name]
            item = items[cat_name]

            defect_rate = max(0.0, RNG.gauss(profile.base_defect_rate, 0.01))
            delay_days = max(0.0, RNG.gauss(profile.base_delay_days, 0.4))
            batch_kg = max(5.0, RNG.gauss(profile.base_batch_kg, 8))
            complaint_count = 1 if RNG.random() < defect_rate * 2 else 0
            rejected_kg = round(batch_kg * defect_rate * RNG.uniform(0.5, 1.5), 2)
            price = round(RNG.uniform(0.9, 1.1) * float(item.unit_price), 2)
            declared_shelf_life = category.expected_shelf_life_days
            expiry_margin = RNG.randint(-1, 1)

            if scenario == "supplier_anomaly" and sname == anomalous_supplier and is_recent:
                # spec example: batch size down, delay up, defect rate up, shelf life down
                batch_kg *= 0.58
                delay_days += 3
                defect_rate += 0.04
                declared_shelf_life = max(1, declared_shelf_life - 6)
                complaint_count += 1

            delivery = SupplierDelivery(
                supplier_id=supplier.id, delivered_at=delivered_at,
                expected_at=delivered_at - timedelta(days=delay_days),
                batch_size_kg=round(batch_kg, 2), delivery_delay_days=round(delay_days, 2),
                defect_rate=round(defect_rate, 4), rejected_quantity_kg=rejected_kg,
                complaint_count=complaint_count, price_per_kg=price,
                remaining_shelf_life_days=declared_shelf_life, expiry_margin_days=expiry_margin,
            )
            db.add(delivery)
            db.flush()

            mfg_date = delivered_at.date() - timedelta(days=RNG.randint(0, 1))
            expiry_date = mfg_date + timedelta(days=declared_shelf_life)
            batch_code = f"{supplier.batch_prefix}-{mfg_date.strftime('%y%m%d')}-{RNG.randint(100,999)}"

            if scenario == "label_fraud" and sname == anomalous_supplier:
                if d == 2 and reused_batch_code is None:
                    reused_batch_code = batch_code  # planted early, will be "reused" much later
                elif is_recent and reused_batch_code is not None:
                    batch_code = reused_batch_code  # duplicate batch code reused months apart -> fraud signal
                    expiry_date = mfg_date + timedelta(days=declared_shelf_life + 25)  # inconsistent shelf life

            storage_unit = assign_storage_for_category(cat_name, units)
            batch = FoodBatch(
                food_item_id=item.id, supplier_id=supplier.id, storage_unit_id=storage_unit.id,
                batch_code=batch_code, quantity=round(batch_kg - rejected_kg, 2),
                manufacturing_date=mfg_date, expiry_date=expiry_date,
                received_at=delivered_at, is_opened=RNG.random() < 0.3,
                status="IN_STOCK",
            )
            db.add(batch)
            delivery.food_batch_id = None  # linked after flush below
            batches.append(batch)
        db.flush()

    return batches


def generate_consumption_and_wastage(db: Session, items: dict[str, FoodItem], days: int, scenario: str):
    now = datetime.now(timezone.utc)
    for name, item in items.items():
        base_qty = RNG.uniform(8, 25)
        for d in range(days):
            ts = now - timedelta(days=days - d)
            qty = max(0.0, RNG.gauss(base_qty, base_qty * 0.08))

            if scenario == "consumption_drop" and name in ("Chicken", "Paneer") and d >= days - 5:
                qty *= 0.35  # sudden, unexplained drop in usage -> possible early spoilage signal

            db.add(ConsumptionRecord(food_item_id=item.id, ts=ts, quantity_consumed=round(qty, 2)))

            if RNG.random() < 0.08:
                wasted = round(RNG.uniform(0.5, 3.0), 2)
                db.add(WastageRecord(
                    food_item_id=item.id, ts=ts, quantity_wasted=wasted,
                    reason="expired" if RNG.random() < 0.6 else "damaged",
                    estimated_loss=round(wasted * float(item.unit_price), 2),
                ))
        db.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario", default="normal",
        choices=["normal", "fridge_drift", "supplier_anomaly", "unit_failure",
                 "label_fraud", "consumption_drop", "all"],
    )
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--no-reset", action="store_true", help="do not drop/recreate tables first")
    args = parser.parse_args()

    print(f"DATA_SOURCE = SYNTHETIC | scenario={args.scenario} | days={args.days}")

    if not args.no_reset:
        print("Resetting schema...")
        reset_schema()

    db = SessionLocal()
    try:
        categories, suppliers, units = seed_reference_data(db)
        items = category_food_items(db, categories)
        profiles = build_supplier_profiles(suppliers)

        scenario = args.scenario
        print("Generating storage readings...")
        generate_storage_readings(db, units, args.days, scenario)

        print("Generating supplier deliveries + food batches...")
        batches = generate_supplier_deliveries_and_batches(
            db, suppliers, profiles, categories, items, units, args.days, scenario
        )

        print("Generating consumption + wastage records...")
        generate_consumption_and_wastage(db, items, args.days, scenario)

        db.commit()
        print(f"Done. {len(batches)} food batches, {len(units)} storage units, "
              f"{len(suppliers)} suppliers, {len(categories)} categories seeded.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
