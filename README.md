# ThoughtLink

Brain-to-robot control system that decodes non-invasive EEG signals into discrete robot commands and demonstrates closed-loop control in a MuJoCo humanoid simulation.

Built for the Kernel & Dimensional VC Track hackathon (18 hours).

## Architecture

```
Browser (Vanilla JS)  ──WebSocket──>  FastAPI Backend  ──>  SimulationBridge  ──>  MuJoCo
     │                                      │
     ├── Web Speech API (STT)               ├── Voice command parser
     ├── EEG waveform canvas                ├── EEG replay / ONNX BrainDecoder
     ├── Factory floor map canvas           ├── Command fusion (voice > brain > idle)
     └── Manual control pad (Direct/BCI)    └── Gear state machine (N/F/R)
```

**Three input channels to control the robot:**
1. **Brain signals (EEG)** — 5-class ONNX classifier decodes Right Fist, Left Fist, Both Fists, Tongue Tapping, Relax into gear-dependent robot actions
2. **Voice commands** — parsed from speech ("move forward", "stop", "turn left", "grab", "shift gear")
3. **Manual controls** — keyboard (WASD) or dashboard buttons, with Direct and BCI control modes

## Quick Start

### Prerequisites
- Python 3.10+
- EEG dataset (900 `.npz` files) at `~/robot_control/data/` or set `THOUGHTLINK_DATA_DIR`
- (Optional) ONNX model at `training/checkpoints/best_5class.onnx` for brain decoding
- (Optional) MuJoCo for simulation

### Install dependencies
```bash
cd ThoughtLink
pip install -r requirements.txt
```

For brain decoding / training, also install:
```bash
pip install torch onnxruntime scikit-learn matplotlib
```

### Environment variables (optional)
Create `.env` in the `ThoughtLink/` root:
```
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```
Without the API key, voice feedback falls back to browser speech synthesis.

### Run the app
```bash
cd ThoughtLink
PYTHONPATH="." python run.py
```

Open **http://localhost:8000** — the backend serves the frontend directly, no npm/build step needed.

### Training (optional)
```bash
cd ThoughtLink
python -m training.data_exploration
python -m training.train_eegnet
python -m training.export_onnx
```

### Simulation demo (standalone)
```bash
cd ThoughtLink
python simulation/demo.py
```

## Dashboard Controls

### Control Modes (toggle with `M` key)

**Direct mode** — explicit commands, 9 buttons:
| Key | Action |
|-----|--------|
| W / Up | Move forward |
| S / Down | Stop |
| A / Left | Rotate left |
| D / Right | Rotate right |
| X | Move backward |
| E | Grab |
| Q | Release |
| G | Shift gear |
| Space | Both Fists (gear-dependent) |
| R | Reset |

**BCI mode** — mirrors the 5 brain signal classes, gear-dependent:
| Key | Brain Class | Action |
|-----|-------------|--------|
| A | Left Fist | Rotate left |
| D | Right Fist | Rotate right |
| W / Space | Both Fists | Forward (F gear) / Backward (R gear) / Grab-Release (N gear) |
| G | Tongue Tapping | Shift gear (N → F → R → N) |
| S | Relax | Idle |

### Gear State Machine
- **Neutral (N)** — Both Fists toggles grab/release
- **Forward (F)** — Both Fists moves forward
- **Reverse (R)** — Both Fists moves backward
- Right/Left Fist always rotates regardless of gear

### Debug Panel
- **BRAIN** toggle — enable/disable brain predictions reaching the robot
- **VOICE** toggle — enable/disable voice input processing
- **TEST EEG** — swap data source to synthetic EEG (goes through real classifier)
- **FULL RESET** — reset all subsystems to initial state
- **Brain Simulator** — inject a specific brain class directly, bypassing EEG + classifier entirely (R.FIST, L.FIST, BOTH, TONGUE, RELAX)

## API

### REST Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | State machine snapshot, sim status, client count |
| GET | `/api/metrics` | Average latency, tick count, loop rate |
| GET | `/api/server-info` | Version, host IP, port, client count |
| GET | `/api/map` | Parsed 2D factory map from MuJoCo scene XML |
| POST | `/api/reset` | Reset state machine only |
| POST | `/api/full-reset` | Full system reset |
| POST | `/api/set-gear/{gear}` | Set gear directly (NEUTRAL/FORWARD/REVERSE) |

### WebSocket (`/ws`)

**Client → Server:**
```json
{"type": "voice_transcript", "text": "move forward", "confidence": 0.95}
{"type": "manual_command", "action": "MOVE_FORWARD"}
{"type": "simulate_brain", "class_index": 0}
{"type": "toggle_brain"}
{"type": "toggle_voice"}
{"type": "toggle_test_mode"}
{"type": "full_reset"}
{"type": "reset"}
{"type": "set_gear", "gear": "FORWARD"}
```

**Server → Client:**
```json
{"type": "state_update", "gear": "NEUTRAL", "action": "IDLE", "brain_class": "Right Fist", "brain_confidence": 0.85, ...}
{"type": "eeg_data", "channels": [[...], ...], "sample_rate": 50}
{"type": "command_log", "source": "brain", "action": "ROTATE_RIGHT", ...}
{"type": "input_toggle_update", "brain_enabled": true, "voice_enabled": true}
{"type": "test_mode_update", "enabled": false}
{"type": "sim_brain_update", "class_index": 0}
{"type": "full_reset_ack"}
{"type": "tts_request", "text": "Moving forward"}
```

## Voice Commands

### Direct Override (immediate execution)
- `stop`, `halt`, `emergency stop`
- `move forward`, `go forward`, `walk`
- `move back`, `reverse`, `go back`
- `turn left`, `rotate left`, `go left`
- `turn right`, `rotate right`, `go right`
- `grab`, `pick up`, `grasp`
- `release`, `drop`, `let go`
- `shift gear`, `change gear`, `next gear`
- `set gear forward`, `set gear reverse`, `set gear neutral`

## Project Structure

```
ThoughtLink/
├── run.py                # Entry point: uvicorn backend.server:app
├── constants.py          # Shared constants (all modules import from here)
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (optional)
├── training/             # ML pipeline
│   ├── preprocessing.py  # EEGPreprocessor, DatasetBuilder
│   ├── model.py          # EEGNet architecture
│   ├── train_eegnet.py   # Training loop
│   ├── realtime.py       # TemporalStabilizer (vote buffer, hysteresis)
│   ├── export_onnx.py    # ONNX export
│   ├── predict.py        # BrainDecoder (public inference API)
│   └── checkpoints/      # .pt and .onnx model files
├── simulation/           # MuJoCo bridge
│   ├── bridge.py         # SimulationBridge class
│   ├── demo.py           # Standalone closed-loop demo
│   └── scenes/           # MuJoCo XML scene files
├── voice/                # Voice command layer
│   ├── command_parser.py # Keyword/regex command parsing
│   ├── voice_input.py    # Voice command listener
│   └── tts_feedback.py   # ElevenLabs TTS with cooldown
├── backend/              # FastAPI server
│   ├── server.py         # App assembly, static file serving
│   ├── control_loop.py   # 10Hz orchestration loop
│   ├── state_machine.py  # Gear state machine (N/F/R)
│   ├── command_fusion.py # Brain + voice merging (priority: voice > brain)
│   ├── eeg_source.py     # EEGReplaySource + TestEEGSource
│   └── api/
│       ├── routes.py     # REST endpoints
│       └── websocket.py  # WebSocket endpoint + broadcast
└── frontend/             # Vanilla JS dashboard (served by FastAPI)
    ├── index.html        # Dashboard layout
    ├── app.js            # WebSocket client, UI state, keyboard controls
    ├── style.css         # Dark theme + responsive breakpoints
    └── components/
        ├── eeg_chart.js  # Canvas 6-channel EEG waveform
        ├── robot_view.js # Canvas 2D factory floor map
        └── voice_status.js # Web Speech API mic wrapper
```

## Team
| Person | Role | Owns |
|--------|------|------|
| Joshua | ML Engineer | `training/` |
| Mourad | Simulation Engineer | `simulation/` |
| Dimitri | Full-Stack Dev | `backend/` + `frontend/` + `voice/` |

## Tech Stack
- **ML:** PyTorch, EEGNet, ONNX Runtime
- **Simulation:** MuJoCo
- **Backend:** FastAPI, WebSocket, uvicorn
- **Voice:** ElevenLabs TTS, Web Speech API (browser STT)
- **Frontend:** Vanilla JavaScript, HTML5 Canvas
