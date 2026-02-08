"""
Simulation Bridge — wraps Mourad's SimulationBridge for the control loop.

Uses the existing simulation/bridge.py::SimulationBridge which connects
to the bri Controller (MuJoCo humanoid sim).
"""

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


class SimBridge:
    """Adapter that wraps Mourad's SimulationBridge for the gear-based control loop."""

    def __init__(self):
        self.bridge = None
        self.running = False
        self.last_action = RobotAction.IDLE
        self.robot_state = {
            "position": [0, 0, 0],
            "orientation": 0,
            "status": "idle",
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
        self.robot_state = {"position": [0, 0, 0], "orientation": 0, "status": "idle"}

    def execute(self, action: RobotAction) -> dict:
        """Send action to simulation, return robot state."""
        self.last_action = action
        bri_name = ACTION_TO_BRI_NAME.get(action, "STOP")

        if self.bridge and SIM_AVAILABLE:
            try:
                self.bridge.send_action(bri_name)
            except Exception as e:
                print(f"[SimBridge] Error sending action: {e}")

        self.robot_state["status"] = action.value.lower()
        return self.robot_state

    def stop(self):
        """Stop the simulation."""
        if self.bridge:
            try:
                self.bridge.stop()
            except Exception:
                pass
        self.running = False

    def get_state(self) -> dict:
        return self.robot_state

    def is_running(self) -> bool:
        if self.bridge and SIM_AVAILABLE:
            return self.bridge.is_running()
        return self.running

    def get_action_log(self) -> list[dict]:
        """Get the action log from the underlying bridge."""
        if self.bridge and SIM_AVAILABLE:
            return self.bridge.get_action_log()
        return []
