import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import get_current_user, require_roles
from app.models.users import RoleEnum
from app.services.simulation import manager, run_scenario_and_broadcast, state

router = APIRouter(tags=["simulation"])


class TriggerRequest(BaseModel):
    scenario: str = "normal"
    days: int = 90


@router.websocket("/ws/live")
async def live_updates(ws: WebSocket):
    """Push channel: dashboard connects here and receives SCENARIO_STARTED /
    SCENARIO_COMPLETE / SCENARIO_FAILED events with no polling."""
    await manager.connect(ws)
    try:
        await ws.send_json({
            "type": "CONNECTED", "scenario": state.scenario,
            "running_job": state.running_job, "last_result": state.last_result,
        })
        while True:
            # keep the connection alive; client isn't expected to send anything
            # meaningful, but reading lets us detect disconnects promptly.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.post(
    "/api/simulation/trigger",
    dependencies=[Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER))],
)
async def trigger_scenario(body: TriggerRequest):
    if state.running_job:
        return {"status": "already_running", "scenario": state.scenario}
    asyncio.create_task(run_scenario_and_broadcast(body.scenario, body.days))
    return {"status": "started", "scenario": body.scenario, "days": body.days}


@router.get("/api/simulation/status", dependencies=[Depends(get_current_user)])
def simulation_status():
    return {
        "scenario": state.scenario, "days": state.days, "running_job": state.running_job,
        "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
        "last_result": state.last_result, "connected_clients": len(manager.active),
    }
