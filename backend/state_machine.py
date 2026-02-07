"""Gear State Machine — core control logic for ThoughtLink."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Gear(Enum):
    NEUTRAL = "NEUTRAL"
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


class RobotAction(Enum):
    IDLE = "IDLE"
    ROTATE_LEFT = "ROTATE_LEFT"
    ROTATE_RIGHT = "ROTATE_RIGHT"
    MOVE_FORWARD = "MOVE_FORWARD"
    MOVE_BACKWARD = "MOVE_BACKWARD"
    GRAB = "GRAB"
    RELEASE = "RELEASE"
    STOP = "STOP"
    EMERGENCY_STOP = "EMERGENCY_STOP"


GEAR_CYCLE = [Gear.NEUTRAL, Gear.FORWARD, Gear.REVERSE]


@dataclass
class RobotState:
    gear: Gear = Gear.NEUTRAL
    holding_item: bool = False
    current_action: RobotAction = RobotAction.IDLE
    last_action_time: float = 0.0
    override_active: bool = False
    override_robot_id: Optional[str] = None


class GearStateMachine:
    def __init__(self):
        self.state = RobotState()
        self._gear_index = 0

    def shift_gear(self) -> Gear:
        """Cycle to next gear. Called on Tongue Tap."""
        self._gear_index = (self._gear_index + 1) % len(GEAR_CYCLE)
        self.state.gear = GEAR_CYCLE[self._gear_index]
        return self.state.gear

    def set_gear(self, gear: Gear) -> Gear:
        """Directly set gear (voice command or API)."""
        self.state.gear = gear
        self._gear_index = GEAR_CYCLE.index(gear)
        return gear

    def resolve_brain_command(self, brain_class: str) -> RobotAction:
        """
        Map a brain signal class + current gear state -> robot action.
        This is the core gear-dependent logic.
        """
        if brain_class == "Right Fist":
            return RobotAction.ROTATE_RIGHT

        elif brain_class == "Left Fist" or brain_class == "Left First":
            return RobotAction.ROTATE_LEFT

        elif brain_class == "Tongue Tapping":
            self.shift_gear()
            return RobotAction.IDLE  # gear shift itself isn't a movement

        elif brain_class == "Both Fists" or brain_class == "Both Firsts":
            if self.state.gear == Gear.FORWARD:
                return RobotAction.MOVE_FORWARD
            elif self.state.gear == Gear.REVERSE:
                return RobotAction.MOVE_BACKWARD
            else:  # NEUTRAL
                return self._toggle_grab()

        elif brain_class == "Relax":
            return RobotAction.IDLE

        return RobotAction.IDLE

    def _toggle_grab(self) -> RobotAction:
        """Toggle grab/release in neutral gear."""
        if self.state.holding_item:
            self.state.holding_item = False
            return RobotAction.RELEASE
        else:
            self.state.holding_item = True
            return RobotAction.GRAB

    def reset(self):
        """Reset state machine to defaults."""
        self.state = RobotState()
        self._gear_index = 0

    def get_state_snapshot(self) -> dict:
        """Return current state for frontend broadcast."""
        return {
            "gear": self.state.gear.value,
            "holding_item": self.state.holding_item,
            "current_action": self.state.current_action.value,
            "override_active": self.state.override_active,
            "override_robot_id": self.state.override_robot_id,
        }
