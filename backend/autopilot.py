"""Autopilot — waypoint navigation for voice-commanded autonomous movement."""

import math
from .state_machine import RobotAction

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import FACTORY_WAYPOINTS, WAYPOINT_ARRIVAL_DIST, WAYPOINT_ALIGN_THRESHOLD


# Aliases for fuzzy matching spoken landmark names
_LANDMARK_ALIASES = {
    "shelf a": "Shelf A",
    "shelf 1": "Shelf A",
    "shelve a": "Shelf A",
    "shelf b": "Shelf B",
    "shelf 2": "Shelf B",
    "shelve b": "Shelf B",
    "conveyor": "Conveyor",
    "conveyor belt": "Conveyor",
    "the conveyor": "Conveyor",
    "belt": "Conveyor",
    "table": "Table",
    "the table": "Table",
    "work table": "Table",
    "pallet 1": "Pallet 1",
    "pallet one": "Pallet 1",
    "source pallet": "Pallet 1",
    "first pallet": "Pallet 1",
    "pallet 2": "Pallet 2",
    "pallet two": "Pallet 2",
    "destination pallet": "Pallet 2",
    "second pallet": "Pallet 2",
}


class Autopilot:
    """Steers the robot toward a named waypoint using turn-then-walk control."""

    def __init__(self, target_name: str, target_xy: tuple[float, float]):
        self.target_name = target_name
        self.target_x, self.target_y = target_xy
        self.active = True
        self.arrived = False
        self.distance = float("inf")

    def update(self, robot_xy, robot_yaw: float) -> RobotAction:
        """Compute next action given current robot pose. Called each tick."""
        if not self.active:
            return RobotAction.IDLE

        rx, ry = float(robot_xy[0]), float(robot_xy[1])
        dx = self.target_x - rx
        dy = self.target_y - ry
        self.distance = math.sqrt(dx * dx + dy * dy)

        if self.distance < WAYPOINT_ARRIVAL_DIST:
            self.active = False
            self.arrived = True
            return RobotAction.STOP

        # Desired heading to target
        desired_yaw = math.atan2(dy, dx)

        # Angle difference normalized to [-pi, pi]
        angle_diff = desired_yaw - robot_yaw
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi

        # Turn to face target, then walk forward
        if abs(angle_diff) > WAYPOINT_ALIGN_THRESHOLD:
            return RobotAction.ROTATE_LEFT if angle_diff > 0 else RobotAction.ROTATE_RIGHT
        else:
            return RobotAction.MOVE_FORWARD

    def cancel(self):
        """Cancel navigation."""
        self.active = False

    def get_status(self) -> dict:
        return {
            "active": self.active,
            "target_name": self.target_name,
            "target_x": self.target_x,
            "target_y": self.target_y,
            "distance": round(self.distance, 2),
            "arrived": self.arrived,
        }

    @staticmethod
    def resolve_target(name: str) -> tuple[str, tuple[float, float]] | None:
        """Resolve a spoken landmark name to (canonical_name, (x, y)) or None."""
        name_lower = name.lower().strip()

        # Try alias table first (exact match)
        if name_lower in _LANDMARK_ALIASES:
            canonical = _LANDMARK_ALIASES[name_lower]
            return canonical, FACTORY_WAYPOINTS[canonical]

        # Try substring match against waypoint names
        for wp_name, coords in FACTORY_WAYPOINTS.items():
            if wp_name.lower() in name_lower or name_lower in wp_name.lower():
                return wp_name, coords

        return None
