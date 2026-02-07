"""
ThoughtLink Simulation Bridge
Connects BrainDecoder inference output to the bri Controller (MuJoCo humanoid sim).
"""

from __future__ import annotations

import sys
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

import numpy as np

from bri import Action, Controller

# Add project root to path for constants import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import (
    BRAIN_LABEL_TO_COMMAND,
    EEG_SAMPLE_RATE,
    WINDOW_SIZE_SAMPLES,
    WINDOW_STRIDE_SAMPLES,
    STIMULUS_START_SAMPLE,
    LABEL_NAMES,
)


@dataclass
class ActionLogEntry:
    """Single entry in the action log."""
    timestamp: float
    window_index: int
    predicted_class: int
    predicted_label: str
    confidence: float
    command: str
    stable_command: str
    latency_ms: float
    gated: bool


class SimulationBridge:
    """
    Connects BrainDecoder output to the bri Controller for closed-loop
    brain-to-robot control in MuJoCo simulation.

    Usage:
        decoder = BrainDecoder(model_path, config_path)
        bridge = SimulationBridge(decoder)
        bridge.start()
        bridge.run_trial("path/to/trial.npz")
        bridge.stop()
    """

    def __init__(
        self,
        decoder=None,
        robot: str = "g1",
        hold_s: float = 0.3,
        forward_speed: float = 0.6,
        yaw_rate: float = 1.5,
        bundle_dir: str | None = None,
        scene: str = "factory",
    ):
        self._decoder = decoder
        self._robot = robot
        self._action_log: list[ActionLogEntry] = []
        self._running = False

        # Resolve bundle directory
        if bundle_dir is None:
            bri_root = Path(__file__).parent / "bri" / "bundles" / f"{robot}_mjlab"
            bundle_dir = str(bri_root)

        self._bundle_dir = Path(bundle_dir)
        self._scene = scene
        self._scene_swapped = False

        # Swap scene.xml to factory_scene.xml if requested
        if scene == "factory":
            self._swap_scene("factory_scene.xml")

        self._controller = Controller(
            backend="sim",
            hold_s=hold_s,
            forward_speed=forward_speed,
            yaw_rate=yaw_rate,
            bundle_dir=bundle_dir,
        )

    def _swap_scene(self, scene_file: str) -> None:
        """Replace scene.xml with the specified scene file for loading."""
        # Look for custom scene in tracked scenes/ directory first, then in bundle
        scenes_dir = Path(__file__).parent / "scenes"
        scene_src = scenes_dir / scene_file
        if not scene_src.exists():
            scene_src = self._bundle_dir / scene_file

        scene_dst = self._bundle_dir / "scene.xml"
        scene_bak = self._bundle_dir / "scene_original.xml"

        if not scene_src.exists():
            print(f"[SimBridge] Warning: {scene_file} not found, using default scene.")
            return

        # Backup original scene.xml if not already backed up
        if scene_dst.exists() and not scene_bak.exists():
            scene_dst.rename(scene_bak)
        elif scene_dst.exists():
            scene_dst.unlink()

        # Copy factory scene as scene.xml
        import shutil
        shutil.copy2(str(scene_src), str(scene_dst))
        self._scene_swapped = True
        print(f"[SimBridge] Using {scene_file} as simulation scene.")

    def _restore_scene(self) -> None:
        """Restore the original scene.xml."""
        if not self._scene_swapped:
            return
        scene_dst = self._bundle_dir / "scene.xml"
        scene_bak = self._bundle_dir / "scene_original.xml"
        if scene_bak.exists():
            if scene_dst.exists():
                scene_dst.unlink()
            scene_bak.rename(scene_dst)
            self._scene_swapped = False

    def start(self) -> None:
        """Start the MuJoCo simulation (opens viewer window)."""
        if self._running:
            return
        print(f"[SimBridge] Starting MuJoCo simulation with {self._robot} robot...")
        self._controller.start()
        self._running = True
        print("[SimBridge] Simulation running. MuJoCo viewer should be open.")

    def stop(self) -> None:
        """Stop the simulation and clean up."""
        if not self._running:
            return
        print("[SimBridge] Stopping simulation...")
        self._controller.stop()
        self._restore_scene()
        self._running = False

    def is_running(self) -> bool:
        """Check if simulation is active."""
        return self._running

    def send_action(self, action_name: str) -> None:
        """
        Send a discrete action to the robot.

        Args:
            action_name: One of "FORWARD", "LEFT", "RIGHT", "STOP"
        """
        if not self._running:
            return
        action = Action.from_str(action_name)
        self._controller.set_action(action)

    def send_action_sustained(self, action_name: str, duration_s: float = 0.25) -> None:
        """
        Send an action and keep refreshing it for the given duration.
        This prevents the hold_s timeout from expiring.

        Args:
            action_name: One of "FORWARD", "LEFT", "RIGHT", "STOP"
            duration_s: How long to sustain the action (seconds)
        """
        if not self._running:
            return
        action = Action.from_str(action_name)
        end_time = time.perf_counter() + duration_s
        while time.perf_counter() < end_time and self._running:
            self._controller.set_action(action)
            time.sleep(0.05)  # refresh at 20Hz, well within hold_s

    def run_trial(self, npz_path: str, realtime: bool = True) -> list[ActionLogEntry]:
        """
        Run closed-loop inference on a recorded trial.

        Loads the .npz file, extracts sliding EEG windows from the stimulus
        period, runs the decoder on each window, and sends the resulting
        action to the robot simulation.

        Args:
            npz_path: Path to the .npz trial file
            realtime: If True, play back at real-time speed (0.25s per window stride)

        Returns:
            List of ActionLogEntry with predictions and actions
        """
        if self._decoder is None:
            raise RuntimeError("No BrainDecoder set. Pass decoder to constructor.")
        if not self._running:
            raise RuntimeError("Simulation not started. Call start() first.")

        self._action_log.clear()
        self._decoder.reset()

        # Load trial data
        data = np.load(npz_path, allow_pickle=True)
        eeg = data["feature_eeg"]  # (7499, 6)
        label_info = data["label"].item()
        trial_label = label_info.get("label", "Unknown")
        duration = label_info.get("duration", 12.0)

        print(f"\n[SimBridge] Running trial: {Path(npz_path).name}")
        print(f"  Label: {trial_label}, Duration: {duration:.1f}s")

        # Extract windows from stimulus period
        stim_start = STIMULUS_START_SAMPLE
        stim_end = min(
            stim_start + int(duration * EEG_SAMPLE_RATE),
            len(eeg)
        )

        window_idx = 0
        pos = stim_start

        while pos + WINDOW_SIZE_SAMPLES <= stim_end:
            window = eeg[pos : pos + WINDOW_SIZE_SAMPLES]  # (500, 6)

            # Run decoder
            t_start = time.perf_counter()
            result = self._decoder.predict(window)
            t_elapsed = (time.perf_counter() - t_start) * 1000  # ms

            # Get the command to send
            command = result.get("stable_command", result.get("command", "STOP"))
            gated = result.get("gated", False)

            # Send to simulation
            if not gated:
                self.send_action(command)
            else:
                self.send_action("STOP")

            # Log
            entry = ActionLogEntry(
                timestamp=time.time(),
                window_index=window_idx,
                predicted_class=result.get("class", -1),
                predicted_label=result.get("label", "Unknown"),
                confidence=result.get("confidence", 0.0),
                command=result.get("command", "STOP"),
                stable_command=command,
                latency_ms=result.get("latency_ms", t_elapsed),
                gated=gated,
            )
            self._action_log.append(entry)

            # Print progress
            status = "GATED" if gated else command
            print(
                f"  Window {window_idx:3d} | "
                f"Pred: {entry.predicted_label:15s} | "
                f"Conf: {entry.confidence:.3f} | "
                f"Action: {status:8s} | "
                f"Latency: {entry.latency_ms:.1f}ms"
            )

            # Advance
            pos += WINDOW_STRIDE_SAMPLES
            window_idx += 1

            # Real-time pacing
            if realtime:
                stride_duration = WINDOW_STRIDE_SAMPLES / EEG_SAMPLE_RATE  # 0.25s
                sleep_time = stride_duration - (t_elapsed / 1000)
                if sleep_time > 0:
                    # Keep refreshing the action during wait
                    end = time.perf_counter() + sleep_time
                    while time.perf_counter() < end and self._running:
                        if not gated:
                            self._controller.set_action(Action.from_str(command))
                        time.sleep(0.05)

        # Stop after trial
        self.send_action("STOP")
        print(f"\n[SimBridge] Trial complete. {len(self._action_log)} windows processed.")

        return list(self._action_log)

    def run_realtime_stream(
        self,
        eeg_stream: Generator[np.ndarray, None, None],
        window_interval_s: float = 0.25,
    ) -> None:
        """
        Process a live/simulated EEG stream.

        Args:
            eeg_stream: Generator yielding (500, 6) EEG windows
            window_interval_s: Time between windows (for pacing)
        """
        if self._decoder is None:
            raise RuntimeError("No BrainDecoder set.")
        if not self._running:
            raise RuntimeError("Simulation not started.")

        self._decoder.reset()
        window_idx = 0

        for window in eeg_stream:
            if not self._running:
                break

            result = self._decoder.predict(window)
            command = result.get("stable_command", result.get("command", "STOP"))
            gated = result.get("gated", False)

            if not gated:
                self.send_action(command)
            else:
                self.send_action("STOP")

            entry = ActionLogEntry(
                timestamp=time.time(),
                window_index=window_idx,
                predicted_class=result.get("class", -1),
                predicted_label=result.get("label", "Unknown"),
                confidence=result.get("confidence", 0.0),
                command=result.get("command", "STOP"),
                stable_command=command,
                latency_ms=result.get("latency_ms", 0.0),
                gated=gated,
            )
            self._action_log.append(entry)
            window_idx += 1

            time.sleep(window_interval_s)

    def get_action_log(self) -> list[dict]:
        """Return the action log as a list of dicts (for API/UI consumption)."""
        return [
            {
                "timestamp": e.timestamp,
                "window_index": e.window_index,
                "predicted_class": e.predicted_class,
                "predicted_label": e.predicted_label,
                "confidence": e.confidence,
                "command": e.command,
                "stable_command": e.stable_command,
                "latency_ms": e.latency_ms,
                "gated": e.gated,
            }
            for e in self._action_log
        ]

    def clear_log(self) -> None:
        """Clear the action log."""
        self._action_log.clear()


def eeg_stream_from_npz(npz_path: str) -> Generator[np.ndarray, None, None]:
    """
    Generator that yields EEG windows from a .npz file,
    simulating a real-time stream.
    """
    data = np.load(npz_path, allow_pickle=True)
    eeg = data["feature_eeg"]
    label_info = data["label"].item()
    duration = label_info.get("duration", 12.0)

    stim_start = STIMULUS_START_SAMPLE
    stim_end = min(
        stim_start + int(duration * EEG_SAMPLE_RATE),
        len(eeg),
    )

    pos = stim_start
    while pos + WINDOW_SIZE_SAMPLES <= stim_end:
        yield eeg[pos : pos + WINDOW_SIZE_SAMPLES]
        pos += WINDOW_STRIDE_SAMPLES
