"""
REST API routes for ThoughtLink.
"""

from fastapi import APIRouter

from backend.services.voice_service import voice_service
from backend.services.simulation_service import simulation_service

router = APIRouter()


@router.get("/status")
async def get_status():
    """System status: simulation running, voice enabled, etc."""
    return {
        "simulation": {
            "running": simulation_service.is_running(),
            "action_log_size": len(simulation_service.get_action_log()),
        },
        "voice": {
            "tts_enabled": voice_service.tts.api_key != "",
            "pending_commands": voice_service.listener.command_queue.qsize(),
        },
    }


@router.get("/action-log")
async def get_action_log():
    """Get the simulation action log."""
    return {"log": simulation_service.get_action_log()}


@router.delete("/action-log")
async def clear_action_log():
    """Clear the simulation action log."""
    simulation_service.clear_log()
    return {"status": "cleared"}


@router.get("/voice/transcript-log")
async def get_transcript_log():
    """Get all received voice transcripts."""
    return {"log": voice_service.listener.get_transcript_log()}


@router.get("/voice/feedback-log")
async def get_feedback_log():
    """Get all TTS feedback events."""
    return {"log": voice_service.tts.get_feedback_log()}


@router.post("/voice/command")
async def send_voice_command(body: dict):
    """
    Manually send a voice command (for testing without microphone).
    Body: {"text": "stop", "confidence": 1.0}
    """
    text = body.get("text", "")
    confidence = body.get("confidence", 1.0)

    parsed = voice_service.process_transcript(text, confidence)
    if parsed:
        if parsed.command_type == "direct_override":
            simulation_service.send_action(parsed.action)
        return {
            "parsed": True,
            "action": parsed.action,
            "command_type": parsed.command_type,
            "robot_id": parsed.robot_id,
            "target": parsed.target,
        }
    return {"parsed": False, "message": "Unrecognized command"}


@router.post("/simulation/action")
async def send_simulation_action(body: dict):
    """
    Send a direct action to the simulation.
    Body: {"action": "FORWARD"}
    """
    action = body.get("action", "STOP")
    simulation_service.send_action(action)
    return {"status": "sent", "action": action}
