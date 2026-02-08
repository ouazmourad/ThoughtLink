# ThoughtLink — Brain-to-Robot Control System

## Overview
ThoughtLink decodes non-invasive brain signals (EEG) into discrete robot commands and demonstrates closed-loop brain-to-robot control using a MuJoCo humanoid simulation. Built for the Kernel & Dimensional VC Track hackathon (18 hours).

## Team
| Person | Role | Owns |
|--------|------|------|
| **Joshua** | ML Engineer (eGPU) | `training/` — preprocessing, models, training, ONNX export, BrainDecoder |
| **Mourad** | Simulation Engineer | `simulation/` — MuJoCo bridge, closed-loop demo |
| **Dimitri** | Full-Stack Dev | `backend/` + `frontend/` — FastAPI API, vanilla JS dashboard |

## Project Structure
```
ThoughtLink/
├── .env                  # Environment variables (ELEVENLABS_API_KEY, etc.)
├── constants.py          # Shared constants — ALL modules import from here
├── requirements.txt      # Python dependencies (single source of truth)
├── run.py                # Entry point: uvicorn backend.server:app
├── training/             # [Joshua] ML pipeline
│   ├── preprocessing.py  # EEGPreprocessor, DatasetBuilder
│   ├── model.py          # EEGNet architecture
│   ├── train_eegnet.py   # Training loop
│   ├── realtime.py       # TemporalStabilizer (vote buffer, hysteresis)
│   ├── export_onnx.py    # ONNX export
│   ├── predict.py        # BrainDecoder — the public inference API
│   ├── config.json       # Preprocessing + inference hyperparameters
│   ├── checkpoints/      # .pt and .onnx model files (best_5class.onnx etc.)
│   └── results/          # Metrics, plots
├── simulation/           # [Mourad] MuJoCo bridge
│   ├── bridge.py         # SimulationBridge class
│   ├── demo.py           # Standalone closed-loop demo
│   └── scenes/           # MuJoCo XML scene files
├── voice/                # [Dimitri] Voice layer
│   ├── config.py         # ElevenLabs API settings, cooldowns, feedback templates
│   ├── command_parser.py # ParsedCommand + CommandParser (keyword/regex matching)
│   ├── voice_input.py    # VoiceCommandListener — receives STT, queues commands
│   └── tts_feedback.py   # VoiceFeedback — ElevenLabs TTS with priority/cooldown
├── backend/              # [Dimitri] FastAPI
│   ├── server.py         # App assembly: creates FastAPI, includes routers, starts control loop
│   ├── config.py         # Server-specific config (imports from constants.py)
│   ├── control_loop.py   # 10Hz orchestration (EEG + voice + sim)
│   ├── state_machine.py  # Gear state machine (N/F/R) + RobotAction enum
│   ├── command_fusion.py # Brain + voice command merging (priority: voice > brain > idle)
│   ├── eeg_source.py     # EEGReplaySource (real data) + TestEEGSource (synthetic test data)
│   ├── sim_bridge.py     # Adapter wrapping simulation/bridge.py
│   ├── scene_parser.py   # MuJoCo scene XML parsing
│   └── api/
│       ├── routes.py     # REST endpoints (status, reset, full-reset, gear, metrics, map)
│       └── websocket.py  # WebSocket endpoint + broadcast + client management
└── frontend/             # [Dimitri] Vanilla JS dashboard
    ├── index.html         # Dashboard HTML (grid layout: gear/brain, map, log, metrics/controls, EEG, voice/debug)
    ├── app.js             # Main JS (WebSocket, UI updates, keyboard controls, debug toggles)
    ├── style.css          # Dark theme styles + responsive breakpoints
    ├── components/
    │   ├── eeg_chart.js   # Canvas EEG waveform (6 channels)
    │   ├── robot_view.js  # Canvas 2D factory map (parsed from MuJoCo XML, zoom, trail)
    │   └── voice_status.js # Web Speech API wrapper (browser mic → transcript)
    └── _react_scaffold/   # Archived incomplete React migration (unused)
```

## Implemented Functionality

### Brain Decode Pipeline (real classifier, no mocks)
- **EEG replay**: `EEGReplaySource` reads 900 .npz files from `../robot_control/data/`, replays at real-time speed through the ONNX classifier
- **ONNX inference**: `BrainDecoder` in `training/predict.py` runs `best_5class.onnx` (CPU or CUDA), ~8ms latency per window
- **Temporal stabilization**: Vote buffer + hysteresis + confidence gating (threshold 0.7) prevents noisy flicker
- **No fallback/demo mode**: If the ONNX model isn't available, brain panel shows `--` (no fake predictions)

### Test EEG Mode
- `TestEEGSource` generates synthetic (500, 6) EEG windows with class-specific frequency patterns
- Data goes through the real ONNX classifier (not bypassing it)
- Cycles through 5 classes every 50 ticks (5 seconds each at 10Hz)
- Toggled via the TEST EEG debug button; requires ONNX model loaded

### Gear State Machine
- Three gears: Neutral (grab/release), Forward (walk), Reverse (backward)
- `Both Fists` brain signal is gear-dependent: forward in F, backward in R, grab toggle in N
- `Tongue Tapping` cycles gears
- `Right/Left Fist` always rotates regardless of gear

### Command Fusion
- Priority: voice commands > brain commands > idle
- Voice commands hold for 2 seconds (`VOICE_OVERRIDE_HOLD_S`)
- Brain commands require `confidence >= 0.7` and stable temporal vote to pass

### Manual Controls
- 9 buttons: directional (FWD, ROT L, ROT R, STOP), grab/release, shift gear, both fists, reset
- Keyboard shortcuts: W/A/S/D, E/Q, G, Space, R
- Manual commands execute directly (bypass voice/fusion pipeline — no duplicate logs)

### Debug Controls (right column, below voice panel)
- **BRAIN toggle**: Enables/disables brain predictions affecting the robot (classifier still runs)
- **VOICE toggle**: Enables/disables voice input processing; stops mic when disabled
- **TEST EEG**: Switches EEG source to synthetic test data through real classifier
- **FULL RESET**: Resets all subsystems — state machine, robot position, voice queue, EEG replay, temporal stabilizer, fusion state, metrics

### Robot Map View
- 2D factory floor parsed from embedded MuJoCo scene XML (shelves, conveyor, table, pallets, bollards)
- Robot follows camera with trail visualization
- Mouse wheel zoom (range 2-12, default 5)
- Legend with category colors, compass, position HUD
- Robot initializes facing east (matching simulation)

### WebSocket Protocol
Messages from frontend to backend:
- `voice_transcript` — mic transcription
- `manual_command` — button/keyboard action
- `reset` — state machine reset only (legacy)
- `set_gear` — direct gear set
- `toggle_brain` / `toggle_voice` / `toggle_test_mode` — debug toggles
- `full_reset` — comprehensive system reset

Messages from backend to frontend:
- `state_update` — every tick: gear, action, brain class/confidence, robot state, latency
- `eeg_data` — every 10th tick: 6-channel decimated EEG for waveform display
- `command_log` — brain/voice action entries
- `test_mode_update` / `input_toggle_update` / `full_reset_ack` — debug state confirmations
- `tts_request` — browser speech synthesis fallback

### REST API
- `GET /api/status` — state machine snapshot, sim status, client count, tick count
- `GET /api/metrics` — avg latency, tick count, loop rate
- `GET /api/server-info` — version, host IP, port, client count
- `GET /api/map` — parsed 2D map data from scene XML
- `POST /api/reset` — state machine reset only
- `POST /api/full-reset` — full system reset
- `POST /api/set-gear/{gear}` — set gear directly (NEUTRAL/FORWARD/REVERSE)

## Dataset
- Location: `../robot_control/data/` (900 .npz files, 511 MB, 20 subjects)
- Each file: 15s recording with EEG (7499, 6) at 500Hz
- Labels: Right Fist, Left Fist, Both Fists, Tongue Tapping, Relax
- Stimulus starts at t=3s (sample 1500)

## Command Mapping
| Brain Label | Class | Robot Action |
|-------------|-------|-------------|
| Right Fist | 0 | ROTATE_RIGHT |
| Left Fist | 1 | ROTATE_LEFT |
| Both Fists | 2 | Gear-dependent (forward/backward/grab) |
| Tongue Tapping | 3 | SHIFT_GEAR |
| Relax | 4 | IDLE |

## Key Integration Points
1. **Joshua -> Dimitri:** `training/predict.py::BrainDecoder` — imported by control_loop.py for real-time inference
2. **Mourad -> Dimitri:** `simulation/bridge.py::SimulationBridge` — wrapped by `backend/sim_bridge.py`
3. **Voice -> Backend:** `voice/command_parser.py::CommandParser` — used directly by `backend/control_loop.py`
4. **Frontend -> Backend:** Vanilla JS dashboard connects via WebSocket (`/ws`) for real-time state updates at 10Hz

## How to Run

### Full app (backend + frontend)
```bash
cd ThoughtLink
PYTHONPATH="." python run.py
# Open http://localhost:8000
```

### Test brain decoder standalone
```bash
cd ThoughtLink
PYTHONPATH="." python -m training.predict
```

### Simulation demo (standalone)
```bash
cd ThoughtLink
python simulation/demo.py
```

### Training
```bash
cd ThoughtLink
python -m training.data_exploration
python -m training.train_baseline
python -m training.train_eegnet
python -m training.export_onnx
```

## Key Constants (from constants.py)
- `EEG_SAMPLE_RATE = 500` Hz
- `WINDOW_SIZE_SAMPLES = 500` (1 second)
- `WINDOW_STRIDE_SAMPLES = 125` (0.25 second)
- `STIMULUS_START_SAMPLE = 1500` (t=3s)
- `CONFIDENCE_THRESHOLD = 0.7`
- `SMOOTHING_WINDOW = 5`
- `HYSTERESIS_COUNT = 3`

## Environment Variables (`.env` in project root)
```
ELEVENLABS_API_KEY=       # Required for TTS. Without it, voice feedback is text-only.
ELEVENLABS_VOICE_ID=      # Optional. Defaults to "Rachel" (21m00Tcm4TlvDq8ikWAM).
```

## Dependencies
- Simulation: `mujoco>=3.4`, `onnxruntime`, `numpy`, `scipy`
- Training: `torch` (CUDA), `scikit-learn`, `onnxruntime-gpu`, `matplotlib`
- Backend: `fastapi`, `uvicorn`, `websockets`, `requests`, `python-dotenv`
- Voice: `requests` (ElevenLabs API calls)
