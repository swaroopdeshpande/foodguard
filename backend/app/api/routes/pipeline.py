from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.users import RoleEnum
from app.schemas.common import PipelineRunResult
from app.services.pipeline import run_full_pipeline

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResult, dependencies=[Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER))])
def trigger_pipeline(db: Session = Depends(get_db)):
    """Runs the full detection pipeline once against current DB state.
    In the live-simulation build (Phase 21) this gets called on every
    WebSocket replay tick instead of manually."""
    return run_full_pipeline(db)
