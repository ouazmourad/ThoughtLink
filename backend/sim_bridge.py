"""
Simulation Bridge — wraps Mourad's SimulationBridge for the control loop.

Supports multi-robot: primary robot uses real SimulationBridge,
secondary robots use dead-reckoning position updates.
"""

import math
import sys
from pathlib import Path
from .state_machine import RobotAction

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Add bri source to path so simulation/bridge.py can find `from bri import ...`
BRI_SRC = PROJECT_ROOT.parent / "brain-robot-interface" / "src"
BRI_BUNDLE_DIR = PROJECT_ROOT.parent / "brain-robot-interface" / "bundles" / "g1_mjlab"
if str(BRI_SRC) not in sys.path:
    sys.path.insert(0, str(BRI_SRC))

try:
    from simulation.bridge import SimulationBridge
    SIM_AVAILABLE = True
except ImportError as e:
    SIM_AVAILABLE = False
    print(f"[SimBridge] WARNING: Cannot import SimulationBridge: {e}")
    print("[SimBridge] Running in stub mode (no actual simulation)")

# Map our gear-aware RobotAction -> bri action names
# bri supports: FORWARD, LEFT, RIGHT, STOP
ACTION_TO_BRI_NAME = {
    RobotAction.MOVE_FORWARD: "FORWARD",
    RobotAction.MOVE_BACKWARD: "STOP",      # sim has no reverse
    RobotAction.ROTATE_LEFT: "LEFT",
    RobotAction.ROTATE_RIGHT: "RIGHT",
    RobotAction.STOP: "STOP",
    RobotAction.EMERGENCY_STOP: "STOP",
    RobotAction.GRAB: "STOP",               # sim has no grab — hold position
    RobotAction.RELEASE: "STOP",
    RobotAction.IDLE: "STOP",
}

# Dead-reckoning constants (per tick at 10Hz)
_DR_MOVE_SPEED = 0.06   # meters per tick
_DR_TURN_SPEED = 0.06   # radians per tick
_DR_FLOOR_LIMIT = 7.5   # max coordinate


class SimBridge:
    """Adapter that wraps Mourad's SimulationBridge for the gear-based control loop.
    Supports multi-robot: primary (robot_0) uses real sim, others use dead-reckoning.
    """

    def __init__(self):
        self.bridge = None
        self.running = False
        self.last_action = RobotAction.IDLE

        # Per-robot states — initialized for primary robot
        self._robot_states: dict[str, dict] = {
            "robot_0": {"position": [0, 0, 0], "orientation": 0, "status": "idle"},
            "robot_1": {"position": [-3.0, 3.0, 0], "orientation": 1.57, "status": "idle"},
            "robot_2": {"position": [3.0, 3.0, 0], "orientation": -1.57, "status": "idle"},
        }

    def start(self):
        """Initialize and start the MuJoCo simulation."""
        if not SIM_AVAILABLE:
            print("[SimBridge] Stub mode — no simulation started")
            self.running = True
            return

        try:
            self.bridge = SimulationBridge(
                decoder=None,  # No decoder — we handle decoding in the control loop
                robot="g1",
                bundle_dir=str(BRI_BUNDLE_DIR),
                scene="factory",
            )
            self.bridge.start()
            self.running = True
            print("[SimBridge] Simulation started via Mourad's SimulationBridge")
        except Exception as e:
            print(f"[SimBridge] Failed to start simulation: {e}")
            print("[SimBridge] Falling back to stub mode")
            self.bridge = None
            self.running = True

    def reset(self):
        self.last_action = RobotAction.IDLE
        self._robot_states = {
            "robot_0": {"position": [0, 0, 0], "orientation": 0, "status": "idle"},
            "robot_1": {"position": [-3.0, 3.0, 0], "orientation": 1.57, "status": "idle"},
            "robot_2": {"position": [3.0, 3.0, 0], "orientation": -1.57, "status": "idle"},
        }

    def execute(self, action: RobotAction, robot_id: str = "robot_0") -> dict:
        """Send action to simulation/dead-reckoning for a specific robot, return robot state."""
        self.last_action = action
        bri_name = ACTION_TO_BRI_NAME.get(action, "STOP")

        if robot_id == "robot_0" and self.bridge and SIM_AVAILABLE:
            # Primary robot uses real simulation
            try:
                self.bridge.send_action(bri_name)
            except Exception as e:
                print(f"[SimBridge] Error sending action: {e}")

            try:
                robot_xy, yaw = self.bridge.get_robot_state()
                self._robot_states["robot_0"]["position"] = [float(robot_xy[0]), float(robot_xy[1]), 0]
                self._robot_states["robot_0"]["orientation"] = float(yaw)
            except Exception:
                pass
        else:
            # Dead-reckoning for secondary robots (or stub mode for primary)
            self._dead_reckon(robot_id, action)

        state = self._robot_states.get(robot_id, self._robot_states["robot_0"])
        state["status"] = action.value.lower()
        return state

    def _dead_reckon(self, robot_id: str, action: RobotAction):
        """Update robot position using simple dead-reckoning."""
        state = self._robot_states.get(robot_id)
        if not state:
            return

        pos = state["position"]
        yaw = state["orientation"]

        if action == RobotAction.MOVE_FORWARD:
            pos[0] += math.cos(yaw) * _DR_MOVE_SPEED
            pos[1] += math.sin(yaw) * _DR_MOVE_SPEED
        elif action == RobotAction.MOVE_BACKWARD:
            pos[0] -= math.cos(yaw) * _DR_MOVE_SPEED
            pos[1] -= math.sin(yaw) * _DR_MOVE_SPEED
        elif action == RobotAction.ROTATE_LEFT:
            yaw += _DR_TURN_SPEED
        elif action == RobotAction.ROTATE_RIGHT:
            yaw -= _DR_TURN_SPEED

        # Clamp to floor bounds
        pos[0] = max(-_DR_FLOOR_LIMIT, min(_DR_FLOOR_LIMIT, pos[0]))
        pos[1] = max(-_DR_FLOOR_LIMIT, min(_DR_FLOOR_LIMIT, pos[1]))

        state["position"] = pos
        state["orientation"] = yaw

    def stop(self):
        """Stop the simulation."""
        if self.bridge:
            try:
                self.bridge.stop()
            except Exception:
                pass
        self.running = False

    def get_state(self, robot_id: str = "robot_0") -> dict:
        if robot_id == "robot_0" and self.bridge and SIM_AVAILABLE:
            try:
                robot_xy, yaw = self.bridge.get_robot_state()
                self._robot_states["robot_0"]["position"] = [float(robot_xy[0]), float(robot_xy[1]), 0]
                self._robot_states["robot_0"]["orientation"] = float(yaw)
            except Exception:
                pass
        return self._robot_states.get(robot_id, self._robot_states["robot_0"])

    def get_all_states(self) -> dict[str, dict]:
        """Return states for all robots."""
        # Sync primary from sim
        self.get_state("robot_0")
        return dict(self._robot_states)

    def is_running(self) -> bool:
        if self.bridge and SIM_AVAILABLE:
            return self.bridge.is_running()
        return self.running

    def get_action_log(self) -> list[dict]:
        """Get the action log from the underlying bridge."""
        if self.bridge and SIM_AVAILABLE:
            return self.bridge.get_action_log()
        return []
