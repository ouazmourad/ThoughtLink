"""Voice Command Parser — parses natural language voice transcripts into robot commands."""

import re

# Ordered list of (pattern, action) — more specific patterns first
VOICE_COMMANDS = [
    # Emergency (highest priority)
    (r"\bemergency\b", "EMERGENCY_STOP"),
    # Gear commands (must match before generic "forward"/"reverse")
    (r"\b(shift gear|next gear|change gear)\b", "SHIFT_GEAR"),
    (r"\b(neutral gear|gear neutral|go neutral)\b", "SET_GEAR_NEUTRAL"),
    (r"\b(forward gear|gear forward|drive mode)\b", "SET_GEAR_FORWARD"),
    (r"\b(reverse gear|gear reverse|back mode)\b", "SET_GEAR_REVERSE"),
    # Stop
    (r"\b(stop|halt|freeze)\b", "STOP"),
    # Movement
    (r"\b(move forward|go forward|go ahead|ahead)\b", "MOVE_FORWARD"),
    (r"\b(move back|go back|backward|move backward)\b", "MOVE_BACKWARD"),
    (r"\b(turn left|rotate left)\b", "ROTATE_LEFT"),
    (r"\b(turn right|rotate right)\b", "ROTATE_RIGHT"),
    # Single-word movement (lower priority)
    (r"\bforward\b", "MOVE_FORWARD"),
    (r"\breverse\b", "MOVE_BACKWARD"),
    (r"\bleft\b", "ROTATE_LEFT"),
    (r"\bright\b", "ROTATE_RIGHT"),
    (r"\bgo\b", "MOVE_FORWARD"),
    # Grab/Release
    (r"\b(grab|pick up|grasp)\b", "GRAB"),
    (r"\b(release|drop|let go|put down)\b", "RELEASE"),
    # Gear single-word fallback
    (r"\bshift\b", "SHIFT_GEAR"),
]


def parse_voice_transcript(text: str) -> dict | None:
    """
    Parse a voice transcript into a structured command.

    Returns dict with command_type and action, or None if no command recognized.
    """
    if not text:
        return None

    text_lower = text.lower().strip()

    for pattern, action in VOICE_COMMANDS:
        if re.search(pattern, text_lower):
            return {
                "command_type": "direct_override",
                "action": action,
                "raw_text": text,
            }

    return None
