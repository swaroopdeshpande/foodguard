import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class LabelScan(Base):
    __tablename__ = "label_scans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("food_batches.id"), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)
