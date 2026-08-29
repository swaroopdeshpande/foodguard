import uuid
from datetime import date

from pydantic import BaseModel


class ReferenceItem(BaseModel):
    id: uuid.UUID
    name: str


class CategoryRef(ReferenceItem):
    required_min_temp_c: float
    required_max_temp_c: float
    expected_shelf_life_days: int


class StorageUnitRef(ReferenceItem):
    target_temp_c: float


class FoodItemRef(ReferenceItem):
    category_id: uuid.UUID
    category_name: str


class ManualBatchCreate(BaseModel):
    food_item_id: uuid.UUID | None = None
    new_food_item_name: str | None = None   # create a new food item on the fly
    category_id: uuid.UUID | None = None    # required if new_food_item_name given
    supplier_id: uuid.UUID
    storage_unit_id: uuid.UUID
    batch_code: str
    quantity: float
    manufacturing_date: date
    expiry_date: date


class ManualReadingCreate(BaseModel):
    storage_unit_id: uuid.UUID
    temperature_c: float
    humidity_pct: float | None = None


class ManualDeliveryCreate(BaseModel):
    supplier_id: uuid.UUID
    batch_size_kg: float
    delivery_delay_days: float = 0
    defect_rate: float = 0
    rejected_quantity_kg: float = 0
    complaint_count: int = 0
    price_per_kg: float = 0
    remaining_shelf_life_days: int = 0
    expiry_margin_days: int = 0


class ManualConsumptionCreate(BaseModel):
    food_item_id: uuid.UUID
    quantity_consumed: float


class ManualEntryResult(BaseModel):
    created_id: uuid.UUID
    risk_prediction: dict | None = None
    label_anomalies: list[dict] = []
    storage_anomaly: dict | None = None
    supplier_anomaly: dict | None = None
    consumption_anomaly: dict | None = None
    incident: dict | None = None
