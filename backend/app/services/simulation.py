"""
Live-simulation broadcast layer (spec Phase 21: "no hardware ... Dashboard
updates without refresh").

Honest framing: there is no physical sensor feed. What's real:
  1. A scenario is (re)generated into Postgres via generate_demo_data.py.
  2. The full detection pipeline runs against that data.
  3. Every connected dashboard gets the new state pushed over WebSocket
     the moment step 2 finishes -- no polling, no manual refresh.

This is what "real-time" means for a hardware-free student project: the
system reacts and pushes instantly when new data lands, same as it would
for a genuine live sensor feed arriving over MQTT/webhook in production.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import WebSocket

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = REPO_ROOT / "scripts" / "generate_demo_data.py"
PYTHON = REPO_ROOT / "backend" / "venv" / "bin" / "python"


@dataclass
class SimulationState:
    scenario: str = "normal"
    days: int = 90
    running_job: bool = False
    last_run_at: datetime | None = None
    last_result: dict | None = None


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
state = SimulationState()


async def run_scenario_and_broadcast(scenario: str, days: int):
    """Regenerates the DB with the chosen scenario, runs the full pipeline,
    then pushes the new dashboard summary + incident count to every
    connected client. Runs the generator as a subprocess (it manages its
    own DB session/engine) so it can't collide with the API's connections.
    """
    state.running_job = True
    state.scenario = scenario
    state.days = days
    await manager.broadcast({"type": "SCENARIO_STARTED", "scenario": scenario, "days": days})

    proc = await asyncio.create_subprocess_exec(
        str(PYTHON), str(GENERATOR), "--scenario", scenario, "--days", str(days),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        state.running_job = False
        await manager.broadcast({
            "type": "SCENARIO_FAILED", "scenario": scenario,
            "error": stderr.decode(errors="replace")[-2000:],
        })
        return

    # run the detection pipeline in a thread (SQLAlchemy session is sync)
    from app.database.session import SessionLocal
    from app.services.pipeline import run_full_pipeline

    def _run():
        db = SessionLocal()
        try:
            return run_full_pipeline(db)
        finally:
            db.close()

    result = await asyncio.to_thread(_run)

    state.running_job = False
    state.last_run_at = datetime.now(timezone.utc)
    state.last_result = result

    await manager.broadcast({
        "type": "SCENARIO_COMPLETE", "scenario": scenario, "days": days,
        "pipeline_result": result, "completed_at": state.last_run_at.isoformat(),
    })
