"""Command Fusion — merges brain + voice commands into a single action."""

import time
from .state_machine import GearStateMachine, RobotAction, Gear
from .config import VOICE_OVERRIDE_HOLD_S


class CommandFusion:
    def __init__(self, state_machine: GearStateMachine):
        self.sm = state_machine
        self.last_emitted_action = RobotAction.IDLE
        self.voice_override_until = 0.0

    def update(self, brain_result: dict | None, voice_command: dict | None) -> dict:
        """
        Called every tick (~10Hz).

        brain_result: from BrainDecoder.predict()
            {"class": "Right Fist", "command": "...", "confidence": 0.84,
             "stable_command": "ROTATE_RIGHT", "gated": False}

        voice_command: parsed voice command dict or None
            {"command_type": "direct_override", "action": "MOVE_FORWARD", ...}

        Returns: {"action": RobotAction, "source": "brain"|"voice"|"idle", ...}
        """
        now = time.time()

        # Priority 1: Voice commands (always trusted)
        if voice_command is not None:
            action = self._handle_voice_command(voice_command)
            if action is not None:
                self.voice_override_until = now + VOICE_OVERRIDE_HOLD_S
                self.last_emitted_action = action
                self.sm.state.current_action = action
                return {
                    "action": action,
                    "source": "voice",
                    "voice_command": voice_command,
                    "timestamp": now,
                }

        # If voice recently gave a command, hold it
        if now < self.voice_override_until:
            return {
                "action": self.last_emitted_action,
                "source": "voice_hold",
                "timestamp": now,
            }

        # Priority 2: Brain commands (gear-dependent)
        if brain_result and not brain_result.get("gated", True):
            stable = brain_result.get("stable_command")
            if stable and stable != "IDLE":
                brain_label = brain_result.get("label", str(brain_result["class"]))
                action = self.sm.resolve_brain_command(brain_label)
                self.sm.state.current_action = action

                self.last_emitted_action = action
                return {
                    "action": action,
                    "source": "brain",
                    "confidence": brain_result.get("confidence", 0),
                    "brain_class": brain_label,
                    "gear": self.sm.state.gear.value,
                    "timestamp": now,
                }

        # Priority 3: No input -> IDLE
        if self.last_emitted_action != RobotAction.IDLE:
            self.last_emitted_action = RobotAction.IDLE
            self.sm.state.current_action = RobotAction.IDLE

        return {
            "action": RobotAction.IDLE,
            "source": "idle",
            "timestamp": now,
        }

    def _handle_voice_command(self, cmd: dict) -> RobotAction | None:
        """Convert a parsed voice command to a robot action."""
        command_type = cmd.get("command_type", "")
        action_str = cmd.get("action", "")

        if command_type == "direct_override":
            action_map = {
                "STOP": RobotAction.STOP,
                "EMERGENCY_STOP": RobotAction.EMERGENCY_STOP,
                "MOVE_FORWARD": RobotAction.MOVE_FORWARD,
                "MOVE_BACKWARD": RobotAction.MOVE_BACKWARD,
                "ROTATE_LEFT": RobotAction.ROTATE_LEFT,
                "ROTATE_RIGHT": RobotAction.ROTATE_RIGHT,
                "GRAB": RobotAction.GRAB,
                "RELEASE": RobotAction.RELEASE,
            }

            if action_str == "SHIFT_GEAR":
                self.sm.shift_gear()
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_FORWARD":
                self.sm.set_gear(Gear.FORWARD)
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_REVERSE":
                self.sm.set_gear(Gear.REVERSE)
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_NEUTRAL":
                self.sm.set_gear(Gear.NEUTRAL)
                return RobotAction.IDLE

            return action_map.get(action_str)

        return None
