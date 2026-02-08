"""
WebSocket endpoint for real-time communication.
Handles: voice transcripts (STT), TTS audio delivery, EEG state updates.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.voice_service import voice_service
from backend.services.simulation_service import simulation_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients
_clients: set[WebSocket] = set()


async def broadcast(message: dict) -> None:
    """Send a message to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    data = json.dumps(message)
    for ws in _clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    logger.info(f"WebSocket client connected. Total: {len(_clients)}")

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")

            if msg_type == "voice_transcript":
                await _handle_voice_transcript(ws, msg)
            elif msg_type == "action":
                await _handle_action(ws, msg)
            elif msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
            else:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _clients.discard(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(_clients)}")


async def _handle_voice_transcript(ws: WebSocket, msg: dict) -> None:
    """Process a voice transcript from browser STT."""
    text = msg.get("text", "")
    confidence = msg.get("confidence", 1.0)

    parsed = voice_service.process_transcript(text, confidence)

    if parsed:
        feedback = voice_service.tts.acknowledge_voice_command(
            f"{parsed.action}" + (f" on {parsed.robot_id}" if parsed.robot_id else "")
        )

        if parsed.command_type == "direct_override":
            simulation_service.send_action(parsed.action)

        response = {
            "type": "voice_command_parsed",
            "action": parsed.action,
            "command_type": parsed.command_type,
            "robot_id": parsed.robot_id,
            "target": parsed.target,
            "item": parsed.item,
            "timestamp": time.time(),
        }

        if feedback and feedback.get("audio_base64"):
            response["tts_audio"] = {
                "audio_base64": feedback["audio_base64"],
                "text": feedback["text"],
                "event_type": feedback["event_type"],
            }

        await ws.send_text(json.dumps(response))
    else:
        feedback = voice_service.tts.announce_unclear()
        response = {
            "type": "voice_command_unrecognized",
            "text": text,
            "timestamp": time.time(),
        }
        if feedback and feedback.get("audio_base64"):
            response["tts_audio"] = {
                "audio_base64": feedback["audio_base64"],
                "text": feedback["text"],
                "event_type": feedback["event_type"],
            }
        await ws.send_text(json.dumps(response))


async def _handle_action(ws: WebSocket, msg: dict) -> None:
    """Handle a direct action command (from dashboard buttons, etc.)."""
    action = msg.get("action", "STOP")
    simulation_service.send_action(action)

    feedback = voice_service.tts.announce_brain_command(action)

    response = {
        "type": "action_executed",
        "action": action,
        "timestamp": time.time(),
    }
    if feedback and feedback.get("audio_base64"):
        response["tts_audio"] = {
            "audio_base64": feedback["audio_base64"],
            "text": feedback["text"],
            "event_type": feedback["event_type"],
        }
    await ws.send_text(json.dumps(response))
