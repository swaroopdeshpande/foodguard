import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class RiskPrediction(Base):
    """ML Model #1 output: food-risk probability, current + future horizons."""

    __tablename__ = "risk_predictions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    food_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_batches.id"), nullable=False, index=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    risk_probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(20), nullable=False)  # LOW/MEDIUM/HIGH
    prediction_horizon: Mapped[str] = mapped_column(String(10), nullable=False, default="now")  # now/24h/48h

    feature_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    top_factors: Mapped[dict] = mapped_column(JSONB, default=dict)  # explainability
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
