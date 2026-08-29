"""
Fully local OCR: Tesseract via pytesseract. No cloud vision API, no key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

import pytesseract
from PIL import Image

from app.core.config import get_settings

settings = get_settings()
pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

DATE_PATTERNS = [
    r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b",   # 12/05/2026, 12-05-26
    r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b",     # 2026-05-12
]
BATCH_PATTERN = r"\b(?:BATCH|LOT|B\/N)[:\s#-]*([A-Z0-9\-]{4,20})\b"


@dataclass
class ExtractedFields:
    product: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    batch_code: str | None = None
    supplier: str | None = None
    raw_dates_found: list[str] = field(default_factory=list)


def _parse_date(raw: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y",
                "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def extract_text(image_bytes: bytes) -> tuple[str, float]:
    """Returns (raw_text, mean_confidence 0-1)."""
    img = Image.open(BytesIO(image_bytes))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    text = " ".join(w for w in data["text"] if w.strip())
    confidences = [int(c) for c in data["conf"] if c not in ("-1", -1)]
    mean_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    return text, mean_conf


def parse_fields(raw_text: str) -> ExtractedFields:
    fields = ExtractedFields()
    upper = raw_text.upper()

    dates_found = []
    for pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, raw_text):
            dates_found.append(m.group(0))
    fields.raw_dates_found = dates_found

    # heuristic: earlier date near "MFG"/"MFD"/"PKD" keyword = mfg date,
    # date near "EXP"/"USE BY"/"BEST BEFORE" = expiry date. Fallback: earliest
    # parsed date = mfg, latest = expiry.
    parsed_dates = [(d, _parse_date(d)) for d in dates_found]
    parsed_dates = [(raw, d) for raw, d in parsed_dates if d is not None]

    mfg_idx = upper.find("MFG")
    if mfg_idx == -1:
        mfg_idx = upper.find("MFD")
    exp_idx = upper.find("EXP")
    if exp_idx == -1:
        exp_idx = upper.find("USE BY")
    if exp_idx == -1:
        exp_idx = upper.find("BEST BEFORE")

    if parsed_dates:
        parsed_dates.sort(key=lambda x: x[1])
        fields.manufacturing_date = parsed_dates[0][1]
        fields.expiry_date = parsed_dates[-1][1] if len(parsed_dates) > 1 else None

    batch_match = re.search(BATCH_PATTERN, upper)
    if batch_match:
        fields.batch_code = batch_match.group(1)

    return fields
