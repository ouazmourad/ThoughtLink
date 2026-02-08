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
│   ├── realtime.py       # TemporalStabilizer
│   ├── export_onnx.py    # ONNX export
│   ├── predict.py        # BrainDecoder — the public inference API
│   ├── checkpoints/      # .pt and .onnx model files
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
│   ├── state_machine.py  # Gear state machine + RobotAction enum
│   ├── command_fusion.py # Brain + voice command merging
│   ├── eeg_source.py     # EEG replay + synthetic fallback
│   ├── sim_bridge.py     # Adapter wrapping simulation/bridge.py
│   ├── scene_parser.py   # MuJoCo scene XML parsing
│   └── api/
│       ├── routes.py     # REST endpoints (status, reset, gear, metrics, map)
│       └── websocket.py  # WebSocket endpoint + broadcast + client management
└── frontend/             # [Dimitri] Vanilla JS dashboard
    ├── index.html         # Dashboard HTML
    ├── app.js             # Main JS (WebSocket, UI updates, keyboard controls)
    ├── style.css          # Styles
    ├── components/
    │   ├── eeg_chart.js   # Canvas EEG waveform
    │   ├── robot_view.js  # Canvas 2D factory map
    │   └── voice_status.js # Web Speech API wrapper
    └── _react_scaffold/   # Archived incomplete React migration
        ├── src/
        ├── package.json
        ├── vite.config.js
        ├── tailwind.config.js
        └── postcss.config.js
```

## Dataset
- Location: `../robot_control/data/` (900 .npz files, 511 MB, 20 subjects)
- Each file: 15s recording with EEG (7499, 6) at 500Hz
- Labels: Right Fist, Left First, Both Firsts, Tongue Tapping, Relax
- Stimulus starts at t=3s (sample 1500)

## Command Mapping
| Brain Label | Class | Robot Action |
|-------------|-------|-------------|
| Right Fist | 0 | RIGHT (turn right) |
| Left First | 1 | LEFT (turn left) |
| Both Firsts | 2 | STOP (halt) |
| Tongue Tapping | 3 | FORWARD (walk) |
| Relax | 4 | STOP (stand still) |

## Key Integration Points
1. **Joshua -> Dimitri:** `training/predict.py::BrainDecoder` — imported by control_loop.py for real-time inference
2. **Mourad -> Dimitri:** `simulation/bridge.py::SimulationBridge` — wrapped by `backend/sim_bridge.py`
3. **Voice -> Backend:** `voice/command_parser.py::CommandParser` — used directly by `backend/control_loop.py`
4. **Frontend -> Backend:** Vanilla JS dashboard connects via WebSocket (`/ws`) for real-time state updates

## How to Run

### Full app (backend + frontend)
```bash
cd ThoughtLink
PYTHONPATH="." python run.py
# Open http://localhost:8000
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
