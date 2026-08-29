import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class FoodBatchOut(BaseModel):
    id: uuid.UUID
    food_item_name: str
    category_name: str
    supplier_name: str
    storage_unit_name: str | None
    batch_code: str
    quantity: float
    manufacturing_date: date
    expiry_date: date
    status: str
    latest_risk_probability: float | None = None
    latest_risk_class: str | None = None
    latest_top_factors: dict | None = None


class StorageUnitOut(BaseModel):
    id: uuid.UUID
    name: str
    unit_type: str
    target_temp_c: float
    current_temperature: float | None = None
    latest_anomaly_type: str | None = None
    latest_severity: str | None = None
    estimated_days_to_threshold: float | None = None


class SupplierOut(BaseModel):
    id: uuid.UUID
    name: str
    latest_anomaly_score: float | None = None
    latest_severity: str | None = None
    deviating_features: dict | None = None


class IncidentOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    source_type: str
    action: str
    department: str
    severity: str
    status: str
    reason_codes: Any
    dimensions_snapshot: dict

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    total_batches_in_stock: int
    high_risk_batches: int
    open_incidents: int
    incidents_by_department: dict[str, int]
    incidents_by_action: dict[str, int]
    estimated_wastage_loss: float
    active_storage_anomalies: int
    active_supplier_anomalies: int


class PipelineRunResult(BaseModel):
    food_risk_incidents: int
    storage_incidents: int
    supplier_incidents: int
    consumption_incidents: int


class LabelScanResult(BaseModel):
    raw_ocr_text: str
    extracted_fields: dict
    ocr_confidence: float | None
    anomalies: list[dict]
