"""Main Control Loop — runs at ~10Hz, orchestrates brain + voice + sim."""

import time
import asyncio
import sys
from pathlib import Path

import numpy as np

from .state_machine import GearStateMachine, RobotAction
from .command_fusion import CommandFusion
from .sim_bridge import SimBridge
from .eeg_source import EEGReplaySource, SyntheticEEGSource
from .voice_parser import parse_voice_transcript
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


class ControlLoop:
    def __init__(self, broadcast_fn):
        self.broadcast = broadcast_fn
        self.state_machine = GearStateMachine()
        self.fusion = CommandFusion(self.state_machine)
        self.sim = SimBridge()

        # Initialize EEG source
        try:
            self.eeg_source = EEGReplaySource(EEG_DATA_DIR)
            if not self.eeg_source.ready:
                self.eeg_source = SyntheticEEGSource()
        except Exception:
            self.eeg_source = SyntheticEEGSource()

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
        parsed = parse_voice_transcript(transcript)
        if parsed:
            async with self._voice_lock:
                self._voice_queue.append(parsed)

    async def push_manual_command(self, action_str: str):
        """Inject a manual command into the fusion pipeline (same path as voice/brain)."""
        if action_str == "SHIFT_GEAR":
            self.state_machine.shift_gear()
            return
        if action_str == "BOTH_FISTS":
            # Gear-dependent: resolve through state machine like a real brain signal
            action = self.state_machine.resolve_brain_command("Both Fists")
            self.sim.execute(action)
            self.state_machine.state.current_action = action
            return
        # For direct actions, push as a synthetic voice command through fusion
        synthetic = {
            "command_type": "direct_override",
            "action": action_str,
            "raw_text": f"[manual] {action_str}",
        }
        async with self._voice_lock:
            self._voice_queue.append(synthetic)

    async def tick(self):
        """Single tick of the control loop."""
        tick_start = time.time()

        # 1. Get EEG prediction
        eeg_window = self.eeg_source.get_latest_window()
        brain_result = None

        if eeg_window is not None:
            if self._brain_decoder:
                # Use Joshua's real BrainDecoder
                try:
                    brain_result = self._brain_decoder.predict(eeg_window)
                except Exception as e:
                    print(f"[ControlLoop] Brain decoder error: {e}")
            else:
                # Demo mode: simulate prediction from EEG label
                label = self.eeg_source.get_current_label()
                label_idx = LABEL_MAP.get(label, 4)
                command = BRAIN_LABEL_TO_COMMAND.get(label_idx, "STOP")
                confidence = 0.75 + 0.2 * np.random.random()
                gated = confidence < CONFIDENCE_THRESHOLD

                brain_result = {
                    "class": label,
                    "label": label,
                    "confidence": float(confidence),
                    "command": command,
                    "stable_command": command if not gated else "IDLE",
                    "gated": gated,
                }

        # 2. Get voice command (non-blocking)
        voice_command = None
        async with self._voice_lock:
            if self._voice_queue:
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
