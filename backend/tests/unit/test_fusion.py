import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.models.incidents import ActionEnum, DepartmentEnum  # noqa: E402
from app.services.fusion import FusionInput, fuse  # noqa: E402


def test_label_fraud_takes_priority_over_everything():
    fi = FusionInput(food_risk_probability=0.9, label_anomaly_types=["POSSIBLE_BATCH_REUSE"])
    out = fuse(fi)
    assert out.action == ActionEnum.FRAUD_REVIEW
    assert out.department == DepartmentEnum.AUDIT


def test_high_food_risk_without_fraud_is_do_not_serve():
    fi = FusionInput(food_risk_probability=0.82)
    out = fuse(fi)
    assert out.action == ActionEnum.DO_NOT_SERVE
    assert out.department == DepartmentEnum.KITCHEN


def test_storage_anomaly_routes_to_maintenance_not_kitchen():
    fi = FusionInput(food_risk_probability=0.1, storage_anomaly_severity="HIGH")
    out = fuse(fi)
    assert out.department == DepartmentEnum.MAINTENANCE
    assert out.action == ActionEnum.MAINTENANCE_ALERT


def test_supplier_anomaly_routes_to_procurement():
    fi = FusionInput(food_risk_probability=0.1, supplier_anomaly_severity="HIGH")
    out = fuse(fi)
    assert out.department == DepartmentEnum.PROCUREMENT
    assert out.action == ActionEnum.SUPPLIER_REVIEW


def test_medium_food_risk_alone_is_check_not_do_not_serve():
    fi = FusionInput(food_risk_probability=0.4)
    out = fuse(fi)
    assert out.action == ActionEnum.CHECK


def test_nothing_triggered_is_safe():
    fi = FusionInput(food_risk_probability=0.05)
    out = fuse(fi)
    assert out.action == ActionEnum.SAFE


def test_consumption_anomaly_never_auto_declares_unsafe():
    """spec section 11: consumption anomaly alone must route to INVESTIGATE, never DO_NOT_SERVE."""
    fi = FusionInput(food_risk_probability=0.1, consumption_anomaly_severity="HIGH")
    out = fuse(fi)
    assert out.action == ActionEnum.INVESTIGATE
    assert out.action != ActionEnum.DO_NOT_SERVE
