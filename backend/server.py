"""ThoughtLink Backend Server — FastAPI + WebSocket."""

import asyncio
import json
import os
import socket
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from .state_machine import Gear
from .control_loop import ControlLoop
from .config import HOST, PORT

app = FastAPI(title="ThoughtLink", version="1.0.0")

# WebSocket connections
connected_clients: list[WebSocket] = []

# Frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")


async def broadcast(message: dict):
    """Send a message to all connected frontend clients."""
    text = json.dumps(message, default=str)
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_text(text)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        if client in connected_clients:
            connected_clients.remove(client)


# Control loop instance
control_loop = ControlLoop(broadcast_fn=broadcast)


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"[Server] Client connected ({len(connected_clients)} total)")

    # Send initial state
    await websocket.send_text(json.dumps({
        "type": "state_update",
        "gear": control_loop.state_machine.state.gear.value,
        "action": "IDLE",
        "action_source": "idle",
        "brain_class": None,
        "brain_confidence": 0,
        "brain_gated": True,
        "holding_item": control_loop.state_machine.state.holding_item,
        "robot_state": control_loop.sim.get_state(),
        "latency_ms": 0,
        "timestamp": time.time(),
    }))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_client_message(message, websocket)
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[Server] Client disconnected ({len(connected_clients)} total)")
    except Exception as e:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[Server] WebSocket error: {e}")


async def handle_client_message(message: dict, websocket: WebSocket):
    """Handle incoming messages from frontend clients."""
    msg_type = message.get("type", "")

    if msg_type == "voice_transcript":
        text = message.get("text", "")
        confidence = message.get("confidence", 1.0)
        if text:
            await control_loop.push_voice_command(text, confidence)
            await broadcast({
                "type": "command_log",
                "source": "voice",
                "text": text,
                "action": "VOICE_INPUT",
                "timestamp": time.time(),
            })

    elif msg_type == "manual_command":
        action = message.get("action", "")
        if action:
            # Route manual commands through the fusion pipeline (same path as voice/brain)
            await control_loop.push_manual_command(action)
            await broadcast({
                "type": "command_log",
                "source": "manual",
                "action": action,
                "timestamp": time.time(),
            })

    elif msg_type == "reset":
        control_loop.state_machine.reset()
        await broadcast({
            "type": "state_update",
            "gear": "NEUTRAL",
            "action": "IDLE",
            "action_source": "idle",
            "brain_class": None,
            "brain_confidence": 0,
            "brain_gated": True,
            "holding_item": False,
            "robot_state": control_loop.sim.get_state(),
            "latency_ms": 0,
            "timestamp": time.time(),
        })

    elif msg_type == "set_gear":
        gear_str = message.get("gear", "NEUTRAL")
        try:
            gear = Gear(gear_str)
            control_loop.state_machine.set_gear(gear)
        except ValueError:
            pass


# --- REST API ---

@app.get("/api/status")
async def get_status():
    return JSONResponse({
        "state": control_loop.state_machine.get_state_snapshot(),
        "sim_running": control_loop.sim.is_running(),
        "clients_connected": len(connected_clients),
        "tick_count": control_loop.tick_count,
    })


@app.post("/api/reset")
async def reset_state():
    control_loop.state_machine.reset()
    return JSONResponse({"status": "ok", "message": "State machine reset"})


@app.post("/api/set-gear/{gear}")
async def set_gear(gear: str):
    try:
        g = Gear(gear.upper())
        control_loop.state_machine.set_gear(g)
        return JSONResponse({"status": "ok", "gear": g.value})
    except ValueError:
        return JSONResponse({"status": "error", "message": f"Invalid gear: {gear}"}, status_code=400)


@app.get("/api/metrics")
async def get_metrics():
    return JSONResponse(control_loop.get_metrics())


def _get_local_ip() -> str:
    """Get the local network IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())


@app.get("/api/server-info")
async def get_server_info():
    return JSONResponse({
        "version": "0.1",
        "host": _get_local_ip(),
        "port": PORT,
        "clients_connected": len(connected_clients),
    })


# --- Static Files ---

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


# Mount static files after routes so API routes take priority
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")


# --- Startup ---

@app.on_event("startup")
async def start_control_loop():
    asyncio.create_task(control_loop.run())
    print("[Server] Control loop started")
