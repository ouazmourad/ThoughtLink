# ThoughtLink

Brain-to-robot control system that decodes non-invasive EEG signals into discrete robot commands and demonstrates closed-loop control in a MuJoCo humanoid simulation.

Built for the Kernel & Dimensional VC Track hackathon (18 hours).

## Architecture

```
Browser (React)  ──WebSocket──>  FastAPI Backend  ──>  SimulationBridge  ──>  MuJoCo
     │                                │
     ├── Web Speech API (STT)         ├── Voice command parser
     ├── Mic button + transcripts     ├── ElevenLabs TTS feedback
     └── Manual control pad           └── EEG BrainDecoder (ONNX)
```

**Three input channels to control the robot:**
1. **Brain signals (EEG)** — decoded by the ML model into FORWARD / LEFT / RIGHT / STOP
2. **Voice commands** — parsed from speech ("R15 move to zone C7", "stop", "turn left")
3. **Manual controls** — dashboard D-pad buttons

## Quick Start

### 1. Backend
```bash
pip install -r backend/requirements.txt
```

Create `.env` in project root:
```
ELEVENLABS_API_KEY=your_key_here
```

Run the server:
```bash
uvicorn backend.main:app --reload --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the dashboard proxies API calls to the backend.

### 3. Simulation (optional, requires MuJoCo)
```bash
python simulation/demo.py --mock
```

## API

### REST Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/status` | System status (sim, voice, TTS) |
| GET | `/api/action-log` | Simulation action log |
| POST | `/api/voice/command` | Send voice command as text |
| POST | `/api/simulation/action` | Send direct action to simulation |

### WebSocket (`/ws`)

**Client → Server:**
```json
{"type": "voice_transcript", "text": "turn left", "confidence": 0.95}
{"type": "action", "action": "FORWARD"}
{"type": "ping"}
```

**Server → Client:**
```json
{"type": "voice_command_parsed", "action": "LEFT", "command_type": "direct_override", "tts_audio": {...}}
{"type": "voice_command_unrecognized", "text": "...", "tts_audio": {...}}
{"type": "action_executed", "action": "FORWARD"}
{"type": "pong"}
```

## Voice Commands

### Direct Override (immediate execution)
- `stop`, `halt`, `emergency stop`
- `move forward`, `turn left`, `turn right`
- `grab`, `release`, `pick up`
- `shift gear`, `set gear forward/reverse/neutral`

### Automated (multi-robot orchestration)
- `R15 move to zone C7`
- `R15 bring box to zone B2`
- `robot 3 pick up box A12`

## Team
| Person | Role | Owns |
|--------|------|------|
| Joshua | ML Engineer | `training/` |
| Mourad | Simulation Engineer | `simulation/` |
| Dimitri | Full-Stack Dev | `backend/` + `frontend/` + `voice/` |

## Tech Stack
- **ML:** PyTorch, EEGNet, ONNX Runtime
- **Simulation:** MuJoCo, bri Controller
- **Backend:** FastAPI, WebSocket, python-dotenv
- **Voice:** ElevenLabs TTS, Web Speech API (STT)
- **Frontend:** React, Vite, Tailwind CSS