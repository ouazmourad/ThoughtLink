"""
Voice service — wraps the voice module for use by the API layer.
Provides a single interface for voice input + TTS feedback.
"""

from __future__ import annotations

from voice.command_parser import CommandParser, ParsedCommand
from voice.voice_input import VoiceCommandListener
from voice.tts_feedback import VoiceFeedback


class VoiceService:
    """
    Central voice service used by REST and WebSocket handlers.
    Holds the command parser, listener, and TTS engine.
    """

    def __init__(self):
        self.parser = CommandParser()
        self.listener = VoiceCommandListener(self.parser)
        self.tts = VoiceFeedback()

    def process_transcript(self, text: str, confidence: float = 1.0) -> ParsedCommand | None:
        """
        Process a speech transcript: parse it, queue the command,
        and return the parsed command (or None).
        """
        return self.listener.on_transcript(text, confidence)

    def get_pending_commands(self) -> list[ParsedCommand]:
        """Get all pending voice commands."""
        return self.listener.get_all_pending()


# Singleton
voice_service = VoiceService()
