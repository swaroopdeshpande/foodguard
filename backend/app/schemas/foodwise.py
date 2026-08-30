import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.food import DataSourceEnum


class DeliveryCreate(BaseModel):
    food_item_id: uuid.UUID | None = None
    new_food_item_name: str | None = None
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID
    storage_unit_id: uuid.UUID
    batch_code: str
    quantity: float
    unit_cost: float | None = None
    manufacturing_date: date
    expiry_date: date
    invoice_number: str | None = None
    received_condition: str | None = None  # ACCEPTED/PARTIALLY_ACCEPTED/REJECTED/QUARANTINED


class ConsumptionCreate(BaseModel):
    food_batch_id: uuid.UUID
    quantity: float
    meal: str | None = None
    department: str | None = None
    allow_expired_override: bool = False
    override_reason: str | None = None


class WasteCreate(BaseModel):
    food_batch_id: uuid.UUID
    quantity: float
    reason: str
    department: str | None = None
    notes: str | None = None


class OccupancyCreate(BaseModel):
    record_date: date
    occupancy_pct: float | None = None
    expected_guests: int | None = None
    actual_guests: int | None = None
    event_type: str | None = None
    notes: str | None = None


class StorageReadingCreate(BaseModel):
    storage_unit_id: uuid.UUID
    temperature_c: float
    humidity_pct: float | None = None
    remarks: str | None = None


class QuarantineCreate(BaseModel):
    reason: str


class StockAdjustmentCreate(BaseModel):
    food_batch_id: uuid.UUID
    delta: float
    reason: str


class BatchSafetyOut(BaseModel):
    batch_id: str
    batch_code: str
    food_item_name: str
    current_quantity: float
    expiry_date: str
    status: str
    reason: str
    can_use: bool


class DemoControlRequest(BaseModel):
    scenario: str = "normal"
    days: int = 90
