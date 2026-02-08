# ThoughtLink — Brain-to-Robot Control System

## Overview
ThoughtLink decodes non-invasive brain signals (EEG) into discrete robot commands and demonstrates closed-loop brain-to-robot control using a MuJoCo humanoid simulation. Built for the Kernel & Dimensional VC Track hackathon (18 hours).

## Team
| Person | Role | Owns |
|--------|------|------|
| **Joshua** | ML Engineer (eGPU) | `training/` — preprocessing, models, training, ONNX export, BrainDecoder |
| **Mourad** | Simulation Engineer | `simulation/` — MuJoCo bridge, closed-loop demo |
| **Dimitri** | Full-Stack Dev | `backend/` + `frontend/` — FastAPI API, React dashboard |

## Project Structure
```
ThoughtLink/
├── .env                  # Environment variables (ELEVENLABS_API_KEY, etc.)
├── constants.py          # Shared constants — ALL modules import from here
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
│   └── bri/              # Cloned brain-robot-interface repo
├── voice/                # [Dimitri] Voice layer
│   ├── config.py         # ElevenLabs API settings, cooldowns, feedback templates
│   ├── command_parser.py # ParsedCommand + CommandParser (keyword/regex matching)
│   ├── voice_input.py    # VoiceCommandListener — receives STT, queues commands
│   └── tts_feedback.py   # VoiceFeedback — ElevenLabs TTS with priority/cooldown
├── backend/              # [Dimitri] FastAPI
│   ├── main.py           # App entry, loads .env, mounts routers
│   ├── requirements.txt  # Python dependencies
│   ├── api/
│   │   ├── routes.py     # REST endpoints (/api/status, /api/voice/command, etc.)
│   │   └── websocket.py  # WebSocket at /ws (voice transcripts, actions, TTS audio)
│   └── services/
│       ├── simulation_service.py  # Wraps SimulationBridge (lazy-loads MuJoCo)
│       └── voice_service.py       # Wraps voice module (parser + listener + TTS)
└── frontend/             # [Dimitri] React + Vite + Tailwind
    ├── src/
    │   ├── App.jsx        # Main dashboard layout
    │   ├── hooks/
    │   │   ├── useWebSocket.js        # WebSocket connection + auto-reconnect
    │   │   └── useVoiceRecognition.js  # Browser Web Speech API wrapper
    │   └── components/
    │       ├── StatusPanel.jsx   # Connection/sim/TTS status dots
    │       ├── VoiceControl.jsx  # Mic button + transcript feed
    │       ├── ControlPad.jsx    # Manual D-pad (FWD/LEFT/RIGHT/STOP)
    │       └── ActionLog.jsx     # Live action log with color-coded badges
    └── package.json
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
1. **Joshua → Mourad:** `training/predict.py::BrainDecoder` — Mourad imports this class in `simulation/bridge.py`
2. **Joshua → Dimitri:** `training/` modules — Dimitri wraps them in `backend/services/`
3. **Mourad → Dimitri:** `simulation/bridge.py::SimulationBridge` — Dimitri wraps in `backend/services/simulation_service.py`
4. **Voice → Backend:** `voice/` module — wrapped by `backend/services/voice_service.py`, exposed via REST + WebSocket
5. **Frontend → Backend:** React dashboard connects via WebSocket (`/ws`) for real-time voice + action updates

## How to Run

### Simulation demo (Mourad)
```bash
cd ThoughtLink
python simulation/demo.py
```

### Backend (Dimitri)
```bash
cd ThoughtLink/backend
uvicorn main:app --reload --port 8000
```

### Frontend (Dimitri)
```bash
cd ThoughtLink/frontend
npm install && npm run dev
```

### Training (Joshua)
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
- Frontend: `react`, `vite`, `tailwindcss`, `recharts`
