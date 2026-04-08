"""
CORTEX — API Server
FastAPI + WebSocket server that streams agent events to the dashboard.
Runs the orchestrator and pushes events in real-time.
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import Orchestrator

app = FastAPI(title="CORTEX API", version="0.1.0")

# Allow dashboard to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
orchestrator: Optional[Orchestrator] = None
connected_clients: list[WebSocket] = []


async def broadcast(message: dict):
    """Send event to all connected dashboard clients."""
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


async def on_agent_event(event: dict):
    """Callback from orchestrator — forwards events to dashboard."""
    await broadcast({
        "type": "agent_event",
        "data": event,
    })


@app.on_event("startup")
async def startup():
    global orchestrator
    orchestrator = Orchestrator(initial_capital=10000.0)
    orchestrator.on_event = on_agent_event


@app.get("/api/status")
async def get_status():
    """Get current system status."""
    return {
        "status": "online",
        "portfolio": orchestrator.portfolio.to_dict() if orchestrator else {},
        "cycle_count": orchestrator.cycle_count if orchestrator else 0,
        "running": orchestrator.running if orchestrator else False,
        "agents": [
            {"name": "Strategist", "role": "strategist", "status": orchestrator.strategist.status},
            {"name": "Risk Officer", "role": "risk_officer", "status": orchestrator.risk_officer.status},
            {"name": "Executor", "role": "executor", "status": orchestrator.executor.status},
            {"name": "Compliance Monitor", "role": "compliance", "status": orchestrator.compliance.status},
        ] if orchestrator else [],
    }


@app.get("/api/events")
async def get_events():
    """Get all events from current session."""
    return {
        "events": orchestrator.event_log if orchestrator else [],
        "count": len(orchestrator.event_log) if orchestrator else 0,
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Get current portfolio state."""
    return orchestrator.portfolio.to_dict() if orchestrator else {}


_METADATA_DIR = os.path.join(os.path.dirname(__file__), "metadata")
_VALID_ROLES = {"strategist", "risk_officer", "executor", "compliance", "auditor"}

@app.get("/api/agents/{role}/metadata")
async def get_agent_metadata(role: str):
    """
    ERC-8004 Agent Registration JSON for the given agent role.
    Roles: strategist, risk_officer, executor, compliance, auditor
    """
    if role not in _VALID_ROLES:
        return JSONResponse(status_code=404, content={"error": f"Unknown role: {role}"})
    path = os.path.join(_METADATA_DIR, f"{role}.json")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Metadata file not found"})
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.get("/api/agents")
async def list_agents_metadata():
    """List metadata URLs for all registered agents."""
    base = "http://localhost:8000"
    return {
        "agents": [
            {"role": role, "metadata_url": f"{base}/api/agents/{role}/metadata"}
            for role in sorted(_VALID_ROLES)
        ]
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    Sends: agent events, portfolio updates, market data.
    Receives: commands (start, stop, etc.)
    """
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"[WS] Dashboard connected. Total clients: {len(connected_clients)}")

    # Send initial state
    await websocket.send_json({
        "type": "init",
        "data": {
            "portfolio": orchestrator.portfolio.to_dict(),
            "agents": [
                {"name": "Strategist", "role": "strategist", "status": "idle"},
                {"name": "Risk Officer", "role": "risk_officer", "status": "idle"},
                {"name": "Executor", "role": "executor", "status": "idle"},
                {"name": "Compliance Monitor", "role": "compliance", "status": "idle"},
            ],
            "events": orchestrator.event_log[-20:],  # Last 20 events
        },
    })

    try:
        while True:
            # Wait for commands from dashboard
            message = await websocket.receive_text()
            cmd = json.loads(message)

            if cmd.get("action") == "start":
                cycles = cmd.get("cycles", 5)
                delay = cmd.get("delay", 10)

                if orchestrator.running:
                    await websocket.send_json({"type": "error", "data": {"message": "Already running"}})
                    continue

                await websocket.send_json({"type": "system", "data": {"message": f"Starting {cycles} cycles..."}})

                # Run orchestrator in background
                asyncio.create_task(run_orchestrator(cycles, delay))

            elif cmd.get("action") == "stop":
                orchestrator.stop()
                await broadcast({"type": "system", "data": {"message": "Trading halted by user"}})

            elif cmd.get("action") == "cycle":
                # Run a single cycle
                if not orchestrator.running:
                    asyncio.create_task(run_single_cycle())

            elif cmd.get("action") == "status":
                status = await get_status()
                await websocket.send_json({"type": "status", "data": status})

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"[WS] Dashboard disconnected. Total clients: {len(connected_clients)}")


async def run_orchestrator(cycles: int, delay: int):
    """Run orchestrator cycles and broadcast updates."""
    orchestrator.running = True
    await broadcast({"type": "system", "data": {"message": "CORTEX online", "running": True}})

    for i in range(cycles):
        if not orchestrator.running:
            break

        # Broadcast cycle start
        await broadcast({
            "type": "cycle_start",
            "data": {"cycle": i + 1, "total": cycles},
        })

        # Get market data and broadcast it
        market_data = await orchestrator.get_market_data()
        await broadcast({
            "type": "market_data",
            "data": market_data,
        })

        # Run the cycle (events are broadcast via on_agent_event callback)
        result = await orchestrator.run_cycle()

        # Broadcast portfolio update after cycle
        await broadcast({
            "type": "portfolio_update",
            "data": orchestrator.portfolio.to_dict(),
        })

        # Broadcast cycle complete
        await broadcast({
            "type": "cycle_complete",
            "data": {"cycle": i + 1, "result": result},
        })

        if i < cycles - 1 and orchestrator.running:
            # Countdown between cycles
            for sec in range(delay, 0, -1):
                await broadcast({
                    "type": "countdown",
                    "data": {"seconds": sec},
                })
                await asyncio.sleep(1)

    orchestrator.running = False
    await broadcast({"type": "system", "data": {"message": "Session complete", "running": False}})


async def run_single_cycle():
    """Run a single trading cycle."""
    orchestrator.running = True
    market_data = await orchestrator.get_market_data()
    await broadcast({"type": "market_data", "data": market_data})
    await orchestrator.run_cycle()
    await broadcast({"type": "portfolio_update", "data": orchestrator.portfolio.to_dict()})
    orchestrator.running = False


# Serve dashboard
dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard")
dashboard_index = os.path.join(dashboard_dir, "index.html")

if os.path.exists(dashboard_index):
    @app.get("/")
    async def serve_dashboard():
        return FileResponse(dashboard_index)
else:
    @app.get("/")
    async def no_dashboard():
        return {"message": "Dashboard not found. Place index.html in ../dashboard/"}


if __name__ == "__main__":
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print("""
+----------------------------------------------+
|                                              |
|     CORTEX - API Server                      |
|     Dashboard: http://localhost:8000         |
|     WebSocket: ws://localhost:8000/ws        |
|                                              |
+----------------------------------------------+
    """)

    uvicorn.run(app, host="0.0.0.0", port=8000)
