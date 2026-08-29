"""
End-to-end pipeline: DB -> features -> ML/anomaly engines -> fusion -> Incidents.

This is what Phase 21's WebSocket replay engine calls on every tick, and what
`scripts/run_pipeline.py` calls once for a static demo pass.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.anomaly.consumption import detect_consumption_anomaly
from app.anomaly.label_fraud import run_all_checks
from app.anomaly.storage_drift import analyze_unit_series
from app.ml.food_risk.features import FEATURE_COLUMNS, build_feature_frame
from app.ml.supplier_anomaly.detect import score_latest_delivery
from app.models.anomalies import ConsumptionAnomaly, LabelAnomaly, StorageAnomaly, SupplierAnomaly
from app.models.incidents import Incident
from app.models.labels import LabelScan
from app.models.risk import RiskPrediction
from app.services.fusion import FusionInput, fuse

MODEL_LATEST = Path(__file__).resolve().parents[3] / "models" / "food_risk" / "latest.json"


def _load_food_risk_model():
    if not MODEL_LATEST.exists():
        return None, None
    meta = json.loads(MODEL_LATEST.read_text())
    model = joblib.load(meta["model_path"])
    return model, meta["version"]


def _risk_class(p: float) -> str:
    if p >= 0.66:
        return "HIGH"
    if p >= 0.31:
        return "MEDIUM"
    return "LOW"


def run_food_risk(db: Session) -> list[Incident]:
    model, version = _load_food_risk_model()
    if model is None:
        return []

    features = build_feature_frame(db)
    incidents = []
    for _, row in features.iterrows():
        X = row[FEATURE_COLUMNS].to_frame().T.astype(float)
        proba = float(model.predict_proba(X)[0, 1])

        top_factors = {}
        if hasattr(model, "feature_importances_"):
            top_factors = dict(sorted(
                zip(FEATURE_COLUMNS, [float(v) for v in model.feature_importances_]),
                key=lambda kv: -kv[1],
            )[:5])

        db.add(RiskPrediction(
            food_batch_id=row.batch_id, risk_probability=round(proba, 4),
            risk_class=_risk_class(proba), prediction_horizon="now",
            feature_snapshot=row[FEATURE_COLUMNS].to_dict(), top_factors=top_factors,
            model_version=version,
        ))

        # label/fraud checks for this batch
        batch_meta = db.execute(text("""
            SELECT b.batch_code, b.manufacturing_date, b.expiry_date, c.expected_shelf_life_days
            FROM food_batches b JOIN food_items fi ON fi.id=b.food_item_id
            JOIN food_categories c ON c.id=fi.category_id WHERE b.id=:bid
        """), {"bid": str(row.batch_id)}).first()
        label_types = []
        if batch_meta:
            findings = run_all_checks(
                db, str(row.batch_id), batch_meta.batch_code,
                batch_meta.manufacturing_date, batch_meta.expiry_date, batch_meta.expected_shelf_life_days,
            )
            if findings:
                # a LabelScan row is required by FK; pipeline runs create a synthetic
                # "batch-record-derived" scan here since no physical OCR photo exists
                # in this automated pass (the OCR endpoint creates real scans separately).
                scan = LabelScan(
                    food_batch_id=row.batch_id, raw_ocr_text=None,
                    extracted_fields={"batch_code": batch_meta.batch_code, "source": "pipeline_consistency_check"},
                    ocr_confidence=None,
                )
                db.add(scan)
                db.flush()
                for f in findings:
                    db.add(LabelAnomaly(
                        label_scan_id=scan.id, food_batch_id=row.batch_id,
                        anomaly_type=f.anomaly_type, severity=f.severity, details=f.details,
                    ))
                    label_types.append(f.anomaly_type)

        fusion_out = fuse(FusionInput(food_risk_probability=proba, label_anomaly_types=label_types))
        incident = Incident(
            source_type="FOOD_RISK", source_id=row.batch_id, action=fusion_out.action,
            department=fusion_out.department, severity=fusion_out.severity,
            reason_codes=fusion_out.reason_codes, dimensions_snapshot=fusion_out.dimensions_snapshot,
        )
        db.add(incident)
        incidents.append(incident)

    db.flush()
    return incidents


def run_storage_anomalies(db: Session) -> list[Incident]:
    units = db.execute(text("SELECT id, name, target_temp_c FROM storage_units")).fetchall()
    incidents = []
    for uid, name, target in units:
        df = pd.read_sql(
            text("SELECT ts, temperature_c FROM storage_readings WHERE storage_unit_id=:u ORDER BY ts"),
            db.bind, params={"u": str(uid)},
        )
        if df.empty:
            continue
        result = analyze_unit_series(df, float(target), float(target) + 2.5, float(target) - 2.5)
        if result.anomaly_type is None:
            continue

        anomaly = StorageAnomaly(
            storage_unit_id=uid, anomaly_type=result.anomaly_type, severity=result.severity,
            current_value=result.current_value, expected_value=result.expected_value,
            residual=result.residual, trend_per_day=result.trend_per_day,
            estimated_days_to_threshold=result.estimated_days_to_threshold, details=result.details,
        )
        db.add(anomaly)
        db.flush()

        fusion_out = fuse(FusionInput(storage_anomaly_severity=result.severity))
        incident = Incident(
            source_type="STORAGE_ANOMALY", source_id=anomaly.id, action=fusion_out.action,
            department=fusion_out.department, severity=fusion_out.severity,
            reason_codes=fusion_out.reason_codes,
            dimensions_snapshot={**fusion_out.dimensions_snapshot, "storage_unit": name},
        )
        db.add(incident)
        incidents.append(incident)
    db.flush()
    return incidents


def run_supplier_anomalies(db: Session) -> list[Incident]:
    suppliers = db.execute(text("SELECT id, name FROM suppliers")).fetchall()
    incidents = []
    for sid, name in suppliers:
        df = pd.read_sql(
            text("SELECT * FROM supplier_deliveries WHERE supplier_id=:s ORDER BY delivered_at"),
            db.bind, params={"s": str(sid)},
        )
        result = score_latest_delivery(df)
        if result is None or not result.is_anomaly:
            continue

        latest_delivery_id = df.iloc[-1]["id"]
        anomaly = SupplierAnomaly(
            supplier_id=sid, supplier_delivery_id=latest_delivery_id,
            anomaly_score=result.anomaly_score, severity=result.severity,
            deviating_features=result.deviating_features, model_version="isoforest-v1",
        )
        db.add(anomaly)
        db.flush()

        fusion_out = fuse(FusionInput(supplier_anomaly_severity=result.severity))
        incident = Incident(
            source_type="SUPPLIER_ANOMALY", source_id=anomaly.id, action=fusion_out.action,
            department=fusion_out.department, severity=fusion_out.severity,
            reason_codes=fusion_out.reason_codes,
            dimensions_snapshot={**fusion_out.dimensions_snapshot, "supplier": name},
        )
        db.add(incident)
        incidents.append(incident)
    db.flush()
    return incidents


def run_consumption_anomalies(db: Session) -> list[Incident]:
    items = db.execute(text("SELECT id, name FROM food_items")).fetchall()
    incidents = []
    for fid, name in items:
        df = pd.read_sql(
            text("""SELECT date_trunc('day', ts) AS day, SUM(quantity_consumed) AS qty
                     FROM consumption_records WHERE food_item_id=:f GROUP BY 1 ORDER BY 1"""),
            db.bind, params={"f": str(fid)},
        )
        if len(df) < 6:
            continue
        result = detect_consumption_anomaly(df["qty"])
        if result is None:
            continue

        anomaly = ConsumptionAnomaly(
            food_item_id=fid, z_score=result.z_score, pct_change=result.pct_change,
            severity=result.severity, recommendation=result.recommendation,
        )
        db.add(anomaly)
        db.flush()

        fusion_out = fuse(FusionInput(consumption_anomaly_severity=result.severity))
        incident = Incident(
            source_type="CONSUMPTION_ANOMALY", source_id=anomaly.id, action=fusion_out.action,
            department=fusion_out.department, severity=fusion_out.severity,
            reason_codes=fusion_out.reason_codes,
            dimensions_snapshot={**fusion_out.dimensions_snapshot, "food_item": name},
        )
        db.add(incident)
        incidents.append(incident)
    db.flush()
    return incidents


def run_full_pipeline(db: Session) -> dict:
    counts = {
        "food_risk_incidents": len(run_food_risk(db)),
        "storage_incidents": len(run_storage_anomalies(db)),
        "supplier_incidents": len(run_supplier_anomalies(db)),
        "consumption_incidents": len(run_consumption_anomalies(db)),
    }
    db.commit()
    return counts
