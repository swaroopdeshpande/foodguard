from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.schemas.common import FoodBatchOut

router = APIRouter(prefix="/api/inventory", tags=["inventory"], dependencies=[Depends(get_current_user)])


@router.get("/batches", response_model=list[FoodBatchOut])
def list_batches(
    db: Session = Depends(get_db),
    category: str | None = None,
    supplier: str | None = None,
    risk_class: str | None = Query(None, description="LOW/MEDIUM/HIGH"),
    limit: int = 100,
):
    sql = """
        SELECT b.id, fi.name AS food_item_name, c.name AS category_name,
               s.name AS supplier_name, su.name AS storage_unit_name,
               b.batch_code, b.quantity, b.manufacturing_date, b.expiry_date, b.status,
               rp.risk_probability, rp.risk_class, rp.top_factors
        FROM food_batches b
        JOIN food_items fi ON fi.id = b.food_item_id
        JOIN food_categories c ON c.id = fi.category_id
        JOIN suppliers s ON s.id = b.supplier_id
        LEFT JOIN storage_units su ON su.id = b.storage_unit_id
        LEFT JOIN LATERAL (
            SELECT risk_probability, risk_class, top_factors FROM risk_predictions rp
            WHERE rp.food_batch_id = b.id ORDER BY predicted_at DESC LIMIT 1
        ) rp ON true
        WHERE b.status = 'IN_STOCK'
    """
    params: dict = {}
    if category:
        sql += " AND c.name = :category"
        params["category"] = category
    if supplier:
        sql += " AND s.name = :supplier"
        params["supplier"] = supplier
    if risk_class:
        sql += " AND rp.risk_class = :risk_class"
        params["risk_class"] = risk_class
    sql += " ORDER BY rp.risk_probability DESC NULLS LAST LIMIT :limit"
    params["limit"] = limit

    rows = db.execute(text(sql), params).mappings().fetchall()
    return [
        FoodBatchOut(
            id=r["id"], food_item_name=r["food_item_name"], category_name=r["category_name"],
            supplier_name=r["supplier_name"], storage_unit_name=r["storage_unit_name"],
            batch_code=r["batch_code"], quantity=float(r["quantity"]),
            manufacturing_date=r["manufacturing_date"], expiry_date=r["expiry_date"], status=r["status"],
            latest_risk_probability=float(r["risk_probability"]) if r["risk_probability"] is not None else None,
            latest_risk_class=r["risk_class"], latest_top_factors=r["top_factors"],
        )
        for r in rows
    ]
