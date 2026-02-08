"""
Simulation service — wraps SimulationBridge for use by the API layer.
Provides a safe interface that works even when MuJoCo is not available.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Map voice/API action names to simulation bridge action names
_ACTION_MAP = {
    "FORWARD": "FORWARD",
    "MOVE_FORWARD": "FORWARD",
    "BACKWARD": "STOP",
    "MOVE_BACKWARD": "STOP",
    "LEFT": "LEFT",
    "ROTATE_LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "ROTATE_RIGHT": "RIGHT",
    "STOP": "STOP",
    "STOP_ALL": "STOP",
    "EMERGENCY_STOP": "STOP",
    "GRAB": "STOP",
    "RELEASE": "STOP",
}


class SimulationService:
    """
    Wraps SimulationBridge. Lazy-loads to avoid MuJoCo import errors
    when running the API without a simulation.
    """

    def __init__(self):
        self._bridge = None
        self._action_log: list[dict] = []

    def _get_bridge(self):
        """Lazy-load SimulationBridge."""
        if self._bridge is not None:
            return self._bridge
        try:
            from simulation.bridge import SimulationBridge
            self._bridge = SimulationBridge()
            return self._bridge
        except ImportError as e:
            logger.warning(f"SimulationBridge not available: {e}")
            return None

    def is_running(self) -> bool:
        if self._bridge is None:
            return False
        return self._bridge.is_running()

    def send_action(self, action: str) -> None:
        """Send an action to the simulation (maps voice actions to bridge actions)."""
        bridge_action = _ACTION_MAP.get(action, "STOP")

        self._action_log.append({
            "action_requested": action,
            "action_sent": bridge_action,
            "source": "api",
        })

        bridge = self._get_bridge()
        if bridge and bridge.is_running():
            bridge.send_action(bridge_action)
        else:
            logger.info(f"Simulation not running. Action logged: {bridge_action}")

    def get_action_log(self) -> list[dict]:
        """Combined log: bridge log + API-initiated actions."""
        bridge = self._get_bridge()
        bridge_log = bridge.get_action_log() if bridge else []
        return bridge_log + self._action_log

    def clear_log(self) -> None:
        self._action_log.clear()
        bridge = self._get_bridge()
        if bridge:
            bridge.clear_log()


# Singleton
simulation_service = SimulationService()
