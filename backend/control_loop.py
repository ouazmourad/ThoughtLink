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

        # Voice command queue
        self._voice_queue: list[dict] = []
        self._voice_lock = asyncio.Lock()

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

    def full_reset(self):
        """Reset all subsystems to initial state."""
        self.state_machine.reset()
        self.sim.reset()
        self._voice_queue.clear()
        if self.eeg_source:
            self.eeg_source.reset()
        if self._test_eeg_source:
            self._test_eeg_source.reset()
        if self._brain_decoder:
            self._brain_decoder.reset()
        self.fusion.voice_override_until = 0.0
        self.latencies.clear()
        self.tick_count = 0
        print("[ControlLoop] Full reset complete")

    async def tick(self):
        """Single tick of the control loop."""
        tick_start = time.time()

        # 1. Get EEG prediction
        source = self._test_eeg_source if self._test_mode else self.eeg_source
        eeg_window = source.get_latest_window() if source else None
        brain_result = None

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

        # 3. Fuse commands
        fused = self.fusion.update(brain_result, voice_command)

        # 4. Execute in simulation
        robot_state = self.sim.execute(fused["action"])

        # 5. Calculate latency
        latency_ms = (time.time() - tick_start) * 1000
        self.latencies.append(latency_ms)
        if len(self.latencies) > 100:
            self.latencies = self.latencies[-100:]

        # 6. Broadcast state to frontend
        await self.broadcast({
            "type": "state_update",
            "gear": self.state_machine.state.gear.value,
            "action": fused["action"].value,
            "action_source": fused["source"],
            "brain_class": brain_result.get("class") if brain_result else None,
            "brain_confidence": brain_result.get("confidence", 0) if brain_result else 0,
            "brain_gated": brain_result.get("gated", True) if brain_result else True,
            "holding_item": self.state_machine.state.holding_item,
            "robot_state": robot_state,
            "latency_ms": round(latency_ms, 1),
            "timestamp": time.time(),
        })

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

        # 8. Log to command log
        if fused["source"] in ("brain", "voice"):
            log_entry = {
                "type": "command_log",
                "source": fused["source"],
                "action": fused["action"].value,
                "timestamp": time.time(),
            }
            if fused["source"] == "brain" and brain_result:
                log_entry["brain_class"] = brain_result.get("class")
                log_entry["confidence"] = brain_result.get("confidence", 0)
            if fused["source"] == "voice" and voice_command:
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
