"""
Fusion engine: combines ML food-risk + all anomaly-detection dimensions into
routed, explainable Incidents. Deliberately keeps every dimension visible
(spec section 13) instead of compressing everything into one number.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.incidents import ActionEnum, DepartmentEnum

# routing table: which department handles which source of finding (spec section 14)
ROUTING = {
    "FOOD_RISK": DepartmentEnum.KITCHEN,
    "STORAGE_ANOMALY": DepartmentEnum.MAINTENANCE,
    "SUPPLIER_ANOMALY": DepartmentEnum.PROCUREMENT,
    "LABEL_ANOMALY": DepartmentEnum.AUDIT,
    "UNIT_INCIDENT": DepartmentEnum.MAINTENANCE,
    "CONSUMPTION_ANOMALY": DepartmentEnum.INVESTIGATION,
}


@dataclass
class FusionInput:
    food_risk_probability: float | None = None
    storage_anomaly_severity: str | None = None       # LOW/MEDIUM/HIGH/None
    supplier_anomaly_severity: str | None = None
    label_anomaly_types: list[str] = field(default_factory=list)
    unit_incident_severity: str | None = None
    consumption_anomaly_severity: str | None = None


@dataclass
class FusionOutput:
    action: ActionEnum
    department: DepartmentEnum
    severity: str
    reason_codes: list[str]
    dimensions_snapshot: dict


def _reason_codes(fi: FusionInput) -> list[str]:
    codes = []
    if fi.food_risk_probability is not None:
        if fi.food_risk_probability >= 0.65:
            codes.append("EXPIRY_NEAR" if fi.food_risk_probability >= 0.8 else "TEMPERATURE_EXPOSURE")
    if fi.storage_anomaly_severity in ("MEDIUM", "HIGH"):
        codes.append("STORAGE_DRIFT")
    if fi.supplier_anomaly_severity in ("MEDIUM", "HIGH"):
        codes.append("SUPPLIER_RISK")
    if fi.label_anomaly_types:
        codes.extend(fi.label_anomaly_types)
    if fi.consumption_anomaly_severity in ("MEDIUM", "HIGH"):
        codes.append("CONSUMPTION_ANOMALY")
    return codes


def fuse(fi: FusionInput) -> FusionOutput:
    """Priority order (highest wins the action+department, but ALL dimensions
    still get recorded in dimensions_snapshot/reason_codes -- nothing is discarded):
      1. Label/fraud findings       -> FRAUD_REVIEW / Audit
      2. Food risk HIGH             -> DO_NOT_SERVE / Kitchen
      3. Unit-level incident        -> MAINTENANCE_ALERT / Maintenance (covers many items at once)
      4. Storage anomaly            -> MAINTENANCE_ALERT / Maintenance
      5. Supplier anomaly           -> SUPPLIER_REVIEW / Procurement
      6. Food risk MEDIUM           -> CHECK or PRIORITY_CHECK / Kitchen
      7. Consumption anomaly only   -> INVESTIGATE / Investigation
      8. Nothing triggered          -> SAFE / Kitchen
    """
    dims = {
        "food_risk": fi.food_risk_probability,
        "storage_anomaly": fi.storage_anomaly_severity,
        "supplier_anomaly": fi.supplier_anomaly_severity,
        "label_anomaly": fi.label_anomaly_types or None,
        "unit_incident": fi.unit_incident_severity,
        "consumption_anomaly": fi.consumption_anomaly_severity,
    }
    codes = _reason_codes(fi)

    if fi.label_anomaly_types:
        return FusionOutput(ActionEnum.FRAUD_REVIEW, DepartmentEnum.AUDIT, "HIGH", codes, dims)

    if fi.food_risk_probability is not None and fi.food_risk_probability >= 0.66:
        return FusionOutput(ActionEnum.DO_NOT_SERVE, DepartmentEnum.KITCHEN, "HIGH", codes, dims)

    if fi.unit_incident_severity in ("MEDIUM", "HIGH"):
        return FusionOutput(
            ActionEnum.MAINTENANCE_ALERT, DepartmentEnum.MAINTENANCE, fi.unit_incident_severity, codes, dims
        )

    if fi.storage_anomaly_severity in ("MEDIUM", "HIGH"):
        return FusionOutput(
            ActionEnum.MAINTENANCE_ALERT, DepartmentEnum.MAINTENANCE, fi.storage_anomaly_severity, codes, dims
        )

    if fi.supplier_anomaly_severity in ("MEDIUM", "HIGH"):
        return FusionOutput(
            ActionEnum.SUPPLIER_REVIEW, DepartmentEnum.PROCUREMENT, fi.supplier_anomaly_severity, codes, dims
        )

    if fi.food_risk_probability is not None and fi.food_risk_probability >= 0.31:
        action = ActionEnum.PRIORITY_CHECK if fi.food_risk_probability >= 0.5 else ActionEnum.CHECK
        return FusionOutput(action, DepartmentEnum.KITCHEN, "MEDIUM", codes, dims)

    if fi.consumption_anomaly_severity in ("MEDIUM", "HIGH"):
        return FusionOutput(
            ActionEnum.INVESTIGATE, DepartmentEnum.INVESTIGATION, fi.consumption_anomaly_severity, codes, dims
        )

    return FusionOutput(ActionEnum.SAFE, DepartmentEnum.KITCHEN, "LOW", codes, dims)
