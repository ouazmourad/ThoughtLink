"""Main Control Loop — runs at ~10Hz, orchestrates brain + voice + sim."""

import time
import asyncio
import sys
from pathlib import Path

import numpy as np

from .state_machine import GearStateMachine, RobotAction
from .command_fusion import CommandFusion
from .sim_bridge import SimBridge
from .eeg_source import EEGReplaySource, TestEEGSource
from .autopilot import Autopilot
from voice.command_parser import CommandParser
from .config import (
    EEG_DATA_DIR,
    TICK_INTERVAL,
    MODEL_PATH,
    MODEL_CONFIG_PATH,
    BRAIN_LABEL_TO_COMMAND,
    LABEL_MAP,
    LABEL_NAMES,
    CONFIDENCE_THRESHOLD,
)

# Try to import Joshua's BrainDecoder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from training.predict import BrainDecoder
    DECODER_AVAILABLE = True
except ImportError:
    DECODER_AVAILABLE = False
    print("[ControlLoop] BrainDecoder not available — using demo mode")


    # Map CommandParser action names to CommandFusion action names
_VOICE_ACTION_MAP = {
    "FORWARD": "MOVE_FORWARD",
    "BACKWARD": "MOVE_BACKWARD",
    "LEFT": "ROTATE_LEFT",
    "RIGHT": "ROTATE_RIGHT",
    "STOP_ALL": "STOP",
}


class ControlLoop:
    def __init__(self, broadcast_fn):
        self.broadcast = broadcast_fn
        self.state_machine = GearStateMachine()
        self.fusion = CommandFusion(self.state_machine)
        self.sim = SimBridge()
        self._voice_parser = CommandParser()

        # Initialize EEG source
        try:
            self.eeg_source = EEGReplaySource(EEG_DATA_DIR)
            if not self.eeg_source.ready:
                self.eeg_source = None
        except Exception:
            self.eeg_source = None

        # Input enable flags
        self.brain_enabled = True
        self.voice_enabled = True

        # Test mode
        self._test_mode = False
        self._test_eeg_source = None

        # Brain simulator (bypasses EEG + classifier entirely)
        self._sim_brain_class = None  # None = off, 0-4 = simulated class index

        # Voice command queue
        self._voice_queue: list[dict] = []
        self._voice_lock = asyncio.Lock()

        # Autopilot (voice-commanded navigation)
        self._autopilot: Autopilot | None = None

        # Metrics
        self.tick_count = 0
        self.latencies: list[float] = []
        self.running = False

        # Brain decoder
        self._brain_decoder = None
        if DECODER_AVAILABLE:
            model_path = Path(MODEL_PATH)
            config_path = Path(MODEL_CONFIG_PATH)
            if model_path.exists():
                try:
                    self._brain_decoder = BrainDecoder(str(model_path), str(config_path))
                    print(f"[ControlLoop] Loaded BrainDecoder from {model_path}")
                except Exception as e:
                    print(f"[ControlLoop] Failed to load BrainDecoder: {e}")

    async def start(self):
        """Start the simulation and begin the control loop."""
        self.sim.start()
        self.running = True
        print("[ControlLoop] Started")

    async def stop(self):
        """Stop the control loop and simulation."""
        self.running = False
        self.sim.stop()
        print("[ControlLoop] Stopped")

    async def push_voice_command(self, transcript: str, confidence: float = 1.0):
        """Queue a voice transcript for processing on next tick."""
        parsed = self._voice_parser.parse(transcript, confidence)
        if parsed:
            action = _VOICE_ACTION_MAP.get(parsed.action, parsed.action)
            async with self._voice_lock:
                self._voice_queue.append({
                    "command_type": parsed.command_type,
                    "action": action,
                    "raw_text": parsed.raw_text,
                })

    async def push_manual_command(self, action_str: str):
        """Inject a manual command — executes directly, bypasses voice/fusion pipeline."""
        if action_str == "SHIFT_GEAR":
            self.state_machine.shift_gear()
            return
        if action_str == "BOTH_FISTS":
            action = self.state_machine.resolve_brain_command("Both Fists")
        else:
            action_map = {
                "MOVE_FORWARD": RobotAction.MOVE_FORWARD,
                "MOVE_BACKWARD": RobotAction.MOVE_BACKWARD,
                "ROTATE_LEFT": RobotAction.ROTATE_LEFT,
                "ROTATE_RIGHT": RobotAction.ROTATE_RIGHT,
                "STOP": RobotAction.STOP,
                "GRAB": RobotAction.GRAB,
                "RELEASE": RobotAction.RELEASE,
            }
            action = action_map.get(action_str, RobotAction.IDLE)
        self.sim.execute(action)
        self.state_machine.state.current_action = action

    def set_test_mode(self, enabled: bool):
        """Enable/disable test EEG mode. Requires ONNX model loaded."""
        if enabled and not self._brain_decoder:
            print("[ControlLoop] Cannot enable test mode — no ONNX model loaded")
            return
        self._test_mode = enabled
        if enabled:
            self._test_eeg_source = TestEEGSource()
            print("[ControlLoop] Test mode ON — synthetic EEG through real classifier")
        else:
            self._test_eeg_source = None
            print("[ControlLoop] Test mode OFF")

    def set_sim_brain(self, class_index: int | None):
        """Set simulated brain class (0-4) or None to disable.
        Bypasses EEG source + classifier entirely."""
        if class_index is not None and not (0 <= class_index < len(LABEL_NAMES)):
            print(f"[ControlLoop] Invalid sim brain class: {class_index}")
            return
        self._sim_brain_class = class_index
        if class_index is not None:
            print(f"[ControlLoop] Brain sim: {LABEL_NAMES[class_index]} (class {class_index})")
        else:
            print("[ControlLoop] Brain sim OFF")

    def start_nav(self, target_name: str) -> dict:
        """Start autopilot navigation to a named waypoint."""
        result = Autopilot.resolve_target(target_name)
        if result is None:
            print(f"[ControlLoop] Unknown nav target: {target_name}")
            return {"ok": False, "error": f"Unknown landmark: {target_name}"}
        canonical_name, (tx, ty) = result
        self._autopilot = Autopilot(canonical_name, (tx, ty))
        # Set gear to forward for walking
        from .state_machine import Gear
        self.state_machine.set_gear(Gear.FORWARD)
        print(f"[ControlLoop] Navigating to {canonical_name} ({tx}, {ty})")
        return {"ok": True, "target": canonical_name, "x": tx, "y": ty}

    def cancel_nav(self):
        """Cancel any active autopilot navigation."""
        if self._autopilot and self._autopilot.active:
            self._autopilot.cancel()
            print("[ControlLoop] Navigation cancelled")
        self._autopilot = None

    def full_reset(self):
        """Reset all subsystems to initial state."""
        self.state_machine.reset()
        self.sim.reset()
        self._voice_queue.clear()
        self._autopilot = None
        if self.eeg_source:
            self.eeg_source.reset()
        if self._test_eeg_source:
            self._test_eeg_source.reset()
        if self._brain_decoder:
            self._brain_decoder.reset()
        self.fusion.voice_override_until = 0.0
        self._sim_brain_class = None
        self.latencies.clear()
        self.tick_count = 0
        print("[ControlLoop] Full reset complete")

    async def tick(self):
        """Single tick of the control loop."""
        tick_start = time.time()

        # 1. Get EEG prediction (or use brain simulator)
        eeg_window = None
        brain_result = None

        if self._sim_brain_class is not None and self.brain_enabled:
            # Brain simulator: bypass EEG + classifier, inject directly
            sim_cls = self._sim_brain_class
            brain_result = {
                "class": sim_cls,
                "label": LABEL_NAMES[sim_cls],
                "command": BRAIN_LABEL_TO_COMMAND.get(sim_cls, "STOP"),
                "confidence": 0.95,
                "probabilities": {LABEL_NAMES[i]: (0.95 if i == sim_cls else 0.01)
                                  for i in range(len(LABEL_NAMES))},
                "latency_ms": 0,
                "stable_command": BRAIN_LABEL_TO_COMMAND.get(sim_cls, "STOP"),
                "gated": False,
                "switched": False,
            }
            # Still get EEG window for waveform display
            source = self._test_eeg_source if self._test_mode else self.eeg_source
            eeg_window = source.get_latest_window() if source else None
        else:
            source = self._test_eeg_source if self._test_mode else self.eeg_source
            eeg_window = source.get_latest_window() if source else None

            if eeg_window is not None and self._brain_decoder:
                try:
                    brain_result = self._brain_decoder.predict(eeg_window)
                except Exception as e:
                    print(f"[ControlLoop] Brain decoder error: {e}")

            # Gate brain result if brain input is disabled
            if not self.brain_enabled:
                brain_result = None

        # 2. Get voice command (non-blocking)
        voice_command = None
        async with self._voice_lock:
            if not self.voice_enabled:
                self._voice_queue.clear()
            elif self._voice_queue:
                voice_command = self._voice_queue.pop(0)

        # 2b. Check if voice command starts/cancels navigation
        nav_started = False
        if voice_command:
            action_str = voice_command.get("action", "")
            if action_str == "NAVIGATE" and voice_command.get("command_type") == "automated":
                target = voice_command.get("target", "")
                result = self.start_nav(target)
                nav_started = result.get("ok", False)
                if nav_started:
                    await self.broadcast({
                        "type": "command_log",
                        "source": "voice",
                        "action": f"NAV → {result['target']}",
                        "text": voice_command.get("raw_text", ""),
                        "timestamp": time.time(),
                    })
                # Don't pass NAVIGATE to fusion — autopilot handles it
                voice_command = None
            elif action_str in ("CANCEL_NAV", "STOP", "EMERGENCY_STOP", "STOP_ALL"):
                # Cancel active navigation on stop commands
                if self._autopilot and self._autopilot.active:
                    self.cancel_nav()
                    await self.broadcast({
                        "type": "command_log",
                        "source": "voice",
                        "action": "NAV CANCELLED",
                        "text": voice_command.get("raw_text", ""),
                        "timestamp": time.time(),
                    })

        # 3. Determine action: autopilot takes priority when active
        if self._autopilot and self._autopilot.active:
            # Read current robot position from sim
            robot_state_now = self.sim.get_state()
            pos = robot_state_now.get("position", [0, 0, 0])
            yaw = robot_state_now.get("orientation", 0)
            action = self._autopilot.update((pos[0], pos[1]), yaw)
            action_source = "autopilot"

            # Check if arrived
            if self._autopilot.arrived:
                await self.broadcast({
                    "type": "command_log",
                    "source": "system",
                    "action": f"ARRIVED at {self._autopilot.target_name}",
                    "timestamp": time.time(),
                })
        else:
            # Normal fusion
            fused = self.fusion.update(brain_result, voice_command)
            action = fused["action"]
            action_source = fused["source"]

        # 4. Execute in simulation
        robot_state = self.sim.execute(action)

        # 5. Calculate latency
        latency_ms = (time.time() - tick_start) * 1000
        self.latencies.append(latency_ms)
        if len(self.latencies) > 100:
            self.latencies = self.latencies[-100:]

        # 6. Broadcast state to frontend
        await self.broadcast({
            "type": "state_update",
            "gear": self.state_machine.state.gear.value,
            "action": action.value,
            "action_source": action_source,
            "brain_class": brain_result.get("label") if brain_result else None,
            "brain_confidence": brain_result.get("confidence", 0) if brain_result else 0,
            "brain_gated": brain_result.get("gated", True) if brain_result else True,
            "holding_item": self.state_machine.state.holding_item,
            "robot_state": robot_state,
            "latency_ms": round(latency_ms, 1),
            "timestamp": time.time(),
        })

        # 6b. Broadcast autopilot navigation status
        if self._autopilot:
            await self.broadcast({
                "type": "nav_update",
                **self._autopilot.get_status(),
            })
            # Clean up finished autopilot
            if not self._autopilot.active:
                self._autopilot = None

        # 7. Broadcast EEG visualization data (every 10th tick = 1Hz)
        if self.tick_count % 10 == 0 and eeg_window is not None:
            try:
                decimated = eeg_window[::10].T.tolist()
                await self.broadcast({
                    "type": "eeg_data",
                    "channels": decimated,
                    "sample_rate": 50,
                })
            except Exception:
                pass

        # 8. Log to command log (only for normal fusion, not autopilot)
        if action_source in ("brain", "voice"):
            log_entry = {
                "type": "command_log",
                "source": action_source,
                "action": action.value,
                "timestamp": time.time(),
            }
            if action_source == "brain" and brain_result:
                log_entry["brain_class"] = brain_result.get("class")
                log_entry["confidence"] = brain_result.get("confidence", 0)
            if action_source == "voice" and voice_command:
                log_entry["text"] = voice_command.get("raw_text", "")
            await self.broadcast(log_entry)

        self.tick_count += 1

    async def run(self):
        """Main loop — runs at ~10Hz."""
        await self.start()
        while self.running:
            try:
                await self.tick()
            except Exception as e:
                print(f"[ControlLoop] Tick error: {e}")
            await asyncio.sleep(TICK_INTERVAL)

    def get_metrics(self) -> dict:
        """Return current performance metrics."""
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        return {
            "avg_latency_ms": round(avg_latency, 1),
            "tick_count": self.tick_count,
            "loop_rate_hz": 10,
            "sim_running": self.sim.is_running(),
        }
