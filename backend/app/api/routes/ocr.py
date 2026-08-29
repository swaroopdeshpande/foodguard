from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.anomaly.label_fraud import check_batch_code_already_exists, check_mfg_before_expiry
from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.labels import LabelScan
from app.ocr.extractor import extract_text, parse_fields
from app.schemas.common import LabelScanResult

router = APIRouter(prefix="/api/ocr", tags=["ocr"], dependencies=[Depends(get_current_user)])


@router.post("/scan", response_model=LabelScanResult)
async def scan_label(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise HTTPException(400, detail="Upload a PNG/JPEG image of the food label")

    image_bytes = await file.read()
    try:
        raw_text, confidence = extract_text(image_bytes)
    except Exception as e:
        raise HTTPException(500, detail=f"OCR failed (is tesseract installed? see README): {e}")

    fields = parse_fields(raw_text)

    scan = LabelScan(
        raw_ocr_text=raw_text,
        extracted_fields={
            "product": fields.product, "batch_code": fields.batch_code,
            "manufacturing_date": str(fields.manufacturing_date) if fields.manufacturing_date else None,
            "expiry_date": str(fields.expiry_date) if fields.expiry_date else None,
            "raw_dates_found": fields.raw_dates_found,
        },
        ocr_confidence=confidence,
    )
    db.add(scan)
    db.flush()

    anomalies = []
    if fields.manufacturing_date and fields.expiry_date:
        finding = check_mfg_before_expiry(fields.manufacturing_date, fields.expiry_date)
        if finding:
            anomalies.append({"anomaly_type": finding.anomaly_type, "severity": finding.severity, "details": finding.details})

    if fields.batch_code:
        # scan.id has no food_batch_id linkage yet at OCR time (that happens once
        # staff confirm which batch this label belongs to) -- this is a soft
        # pre-confirm heads-up, not the full gap-based reuse check (that runs
        # later in the pipeline once the batch record actually exists).
        finding = check_batch_code_already_exists(db, fields.batch_code)
        if finding:
            anomalies.append({"anomaly_type": finding.anomaly_type, "severity": finding.severity, "details": finding.details})

    db.commit()

    return LabelScanResult(
        raw_ocr_text=raw_text, extracted_fields=scan.extracted_fields,
        ocr_confidence=confidence, anomalies=anomalies,
    )
