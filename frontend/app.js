/**
 * ThoughtLink Dashboard — Main Application
 * WebSocket client + UI state management + keyboard controls
 */

// --- WebSocket ---
let ws = null;
let wsReconnectTimer = null;
let connected = false;
let tickCount = 0;

// --- Components ---
let eegChart = null;
let robotView = null;
let voiceManager = null;

// --- State ---
let currentGear = 'NEUTRAL';
let currentAction = 'IDLE';
let brainEnabled = true;
let voiceEnabled = true;
let testModeActive = false;
let simBrainClass = null;  // null = off, 0-4 = simulated class
let controlMode = 'direct'; // 'direct' = explicit commands, 'bci' = gear-dependent brain schema

// ========================
// WebSocket Connection
// ========================

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws`;

    try {
        ws = new WebSocket(wsUrl);
    } catch (e) {
        console.error('[WS] Connection error:', e);
        scheduleReconnect();
        return;
    }

    ws.onopen = () => {
        connected = true;
        updateConnectionStatus(true);
        console.log('[WS] Connected');
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
    };

    ws.onclose = () => {
        connected = false;
        updateConnectionStatus(false);
        console.log('[WS] Disconnected');
        scheduleReconnect();
    };

    ws.onerror = (err) => {
        console.error('[WS] Error:', err);
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleServerMessage(msg);
        } catch (e) {
            console.error('[WS] Parse error:', e);
        }
    };
}

function scheduleReconnect() {
    if (wsReconnectTimer) return;
    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        connectWebSocket();
    }, 2000);
}

function updateConnectionStatus(isConnected) {
    const dot = document.getElementById('conn-dot');
    const text = document.getElementById('conn-text');
    if (dot) dot.classList.toggle('connected', isConnected);
    if (text) text.textContent = isConnected ? 'Connected' : 'Disconnected';
}

function wsSend(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    }
}

// ========================
// Message Handlers
// ========================

function handleServerMessage(msg) {
    switch (msg.type) {
        case 'state_update':
            handleStateUpdate(msg);
            break;
        case 'eeg_data':
            handleEEGData(msg);
            break;
        case 'command_log':
            handleCommandLog(msg);
            break;
        case 'tts_request':
            handleTTSRequest(msg);
            break;
        case 'test_mode_update':
            testModeActive = msg.enabled;
            updateToggleButton('btn-test-mode', testModeActive);
            break;
        case 'input_toggle_update':
            brainEnabled = msg.brain_enabled;
            voiceEnabled = msg.voice_enabled;
            updateToggleButton('btn-brain', brainEnabled);
            updateToggleButton('btn-voice', voiceEnabled);
            break;
        case 'sim_brain_update':
            simBrainClass = msg.class_index;
            updateSimBrainUI(simBrainClass);
            break;
        case 'full_reset_ack':
            if (robotView) robotView.reset();
            tickCount = 0;
            simBrainClass = null;
            updateSimBrainUI(null);
            addLogEntry('system', 'FULL_RESET', 'Full system reset', Date.now() / 1000);
            break;
        default:
            break;
    }
}

function handleStateUpdate(msg) {
    tickCount++;

    // Gear display
    updateGearDisplay(msg.gear);

    // Brain decode panel
    updateBrainPanel(msg.brain_class, msg.brain_confidence, msg.brain_gated, msg.action);

    // Action overlay
    updateActionOverlay(msg.action, msg.action_source);

    // Holding indicator
    updateHoldingIndicator(msg.holding_item);

    // Robot view
    if (robotView) {
        robotView.updateState(msg.robot_state, msg.action);
    }

    // Metrics
    updateMetrics(msg.latency_ms, msg.action_source);

    currentAction = msg.action;
}

function handleEEGData(msg) {
    if (eegChart && msg.channels) {
        eegChart.pushData(msg.channels);
    }
}

function handleCommandLog(msg) {
    addLogEntry(msg.source, msg.action, msg.text, msg.timestamp);
}

function handleTTSRequest(msg) {
    // Use browser speech synthesis as fallback
    if ('speechSynthesis' in window && msg.text) {
        const utterance = new SpeechSynthesisUtterance(msg.text);
        utterance.rate = 1.2;
        utterance.pitch = 0.9;
        speechSynthesis.speak(utterance);
    }
}

// ========================
// UI Updates
// ========================

function updateGearDisplay(gear) {
    if (gear === currentGear) return;
    currentGear = gear;

    const gears = { N: 'NEUTRAL', F: 'FORWARD', R: 'REVERSE' };
    const gearMap = { NEUTRAL: 'N', FORWARD: 'F', REVERSE: 'R' };
    const gearClasses = { NEUTRAL: 'neutral', FORWARD: 'forward', REVERSE: 'reverse' };

    ['N', 'F', 'R'].forEach(g => {
        const el = document.getElementById('gear-' + g);
        if (el) {
            const isActive = gearMap[gear] === g;
            el.className = 'gear-label' + (isActive ? ` active ${gearClasses[gear]}` : '');
        }
    });

    const gearText = document.getElementById('gear-text');
    if (gearText) {
        gearText.textContent = gear;
        gearText.className = 'gear-text ' + gearClasses[gear];
    }

    // Update BOTH button hint in BCI mode
    if (controlMode === 'bci') {
        var bothBtn = document.getElementById('btn-both');
        if (bothBtn) {
            var hint = bothBtn.querySelector('.key-hint');
            if (hint) hint.textContent = 'W — ' + getBothHint();
        }
    }
}

function updateBrainPanel(brainClass, confidence, gated, action) {
    const classEl = document.getElementById('brain-class');
    const fillEl = document.getElementById('confidence-fill');
    const valueEl = document.getElementById('confidence-value');
    const cmdEl = document.getElementById('brain-command');
    const badgeEl = document.getElementById('stable-badge');

    if (classEl) classEl.textContent = brainClass || '--';

    const pct = Math.round((confidence || 0) * 100);
    if (fillEl) fillEl.style.width = pct + '%';
    if (valueEl) valueEl.textContent = pct + '%';
    if (cmdEl) cmdEl.textContent = action || '--';

    if (badgeEl) {
        if (gated) {
            badgeEl.textContent = 'GATED';
            badgeEl.className = 'stable-badge gated';
        } else if (confidence > 0.7) {
            badgeEl.textContent = 'STABLE';
            badgeEl.className = 'stable-badge stable';
        } else {
            badgeEl.textContent = 'UNSTABLE';
            badgeEl.className = 'stable-badge unstable';
        }
    }
}

function updateActionOverlay(action, source) {
    const el = document.getElementById('action-overlay');
    if (!el) return;

    el.textContent = action || 'IDLE';

    let cls = 'idle';
    if (action === 'MOVE_FORWARD' || action === 'MOVE_BACKWARD') cls = 'moving';
    else if (action === 'ROTATE_LEFT' || action === 'ROTATE_RIGHT') cls = 'rotating';
    else if (action === 'GRAB' || action === 'RELEASE') cls = 'grabbing';
    else if (action === 'STOP' || action === 'EMERGENCY_STOP') cls = 'stopped';

    el.className = 'action-overlay ' + cls;
}

function updateHoldingIndicator(holding) {
    const icon = document.getElementById('holding-icon');
    const text = document.getElementById('holding-text');
    if (icon) icon.innerHTML = holding ? '&#9632;' : '&#9633;';
    if (text) {
        text.textContent = holding ? 'Holding item' : 'Not holding';
        text.style.color = holding ? '#a855f7' : '';
    }
}

function updateMetrics(latencyMs, source) {
    const latencyEl = document.getElementById('metric-latency');
    const fpsEl = document.getElementById('metric-fps');
    const ticksEl = document.getElementById('metric-ticks');
    const sourceEl = document.getElementById('metric-source');

    if (latencyEl) latencyEl.textContent = Math.round(latencyMs || 0);
    if (fpsEl) fpsEl.textContent = '10';
    if (ticksEl) ticksEl.textContent = tickCount;
    if (sourceEl) {
        sourceEl.textContent = (source || '--').toUpperCase();
        const colors = { brain: '#06b6d4', voice: '#a855f7', idle: '#64748b', manual: '#eab308' };
        sourceEl.style.color = colors[source] || '#64748b';
    }
}

// ========================
// Command Log
// ========================

let logEntryCount = 0;
const MAX_LOG_ENTRIES = 100;

function addLogEntry(source, action, text, timestamp) {
    const log = document.getElementById('command-log');
    if (!log) return;

    const time = new Date((timestamp || Date.now() / 1000) * 1000);
    const timeStr = time.toLocaleTimeString('en-US', { hour12: false });

    const entry = document.createElement('div');
    entry.className = 'log-entry ' + (source || 'idle');
    entry.innerHTML = `
        <span class="log-time">${timeStr}</span>
        <span class="log-source ${source || ''}">[${(source || '?').toUpperCase()}]</span>
        <span class="log-action">${text || action || '?'}</span>
    `;

    log.appendChild(entry);
    logEntryCount++;

    // Trim old entries
    while (logEntryCount > MAX_LOG_ENTRIES && log.firstChild) {
        log.removeChild(log.firstChild);
        logEntryCount--;
    }

    // Auto-scroll
    log.scrollTop = log.scrollHeight;
}

// ========================
// Manual Controls
// ========================

function sendCommand(action) {
    wsSend({ type: 'manual_command', action: action });
}

function sendReset() {
    wsSend({ type: 'reset' });
}

function toggleControlMode() {
    controlMode = controlMode === 'direct' ? 'bci' : 'direct';
    renderManualControls();
}

function getBothHint() {
    if (currentGear === 'FORWARD') return 'FWD';
    if (currentGear === 'REVERSE') return 'BWD';
    return 'Grab';
}

function renderManualControls() {
    var grid = document.getElementById('manual-controls-grid');
    var badge = document.getElementById('control-mode-badge');
    if (!grid) return;

    if (controlMode === 'bci') {
        if (badge) {
            badge.textContent = 'BCI [M]';
            badge.classList.add('mode-bci');
        }
        grid.innerHTML =
            '<div class="ctrl-btn" onclick="sendCommand(\'ROTATE_LEFT\')">L.FIST<span class="key-hint">A — Rot L</span></div>' +
            '<div class="ctrl-btn accent" id="btn-both" onclick="sendCommand(\'BOTH_FISTS\')">BOTH<span class="key-hint">W — ' + getBothHint() + '</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'ROTATE_RIGHT\')">R.FIST<span class="key-hint">D — Rot R</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'SHIFT_GEAR\')">TONGUE<span class="key-hint">G — Shift</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'STOP\')">RELAX<span class="key-hint">S — Idle</span></div>' +
            '<div class="ctrl-btn" onclick="sendReset()">RESET<span class="key-hint">R</span></div>';
    } else {
        if (badge) {
            badge.textContent = 'DIRECT [M]';
            badge.classList.remove('mode-bci');
        }
        grid.innerHTML =
            '<div class="ctrl-btn" onclick="sendCommand(\'ROTATE_LEFT\')">ROT L<span class="key-hint">A</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'MOVE_FORWARD\')">FWD<span class="key-hint">W</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'ROTATE_RIGHT\')">ROT R<span class="key-hint">D</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'GRAB\')">GRAB<span class="key-hint">E</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'STOP\')">STOP<span class="key-hint">S</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'RELEASE\')">REL<span class="key-hint">Q</span></div>' +
            '<div class="ctrl-btn accent" onclick="sendCommand(\'SHIFT_GEAR\')">SHIFT<span class="key-hint">G</span></div>' +
            '<div class="ctrl-btn" onclick="sendCommand(\'BOTH_FISTS\')">BOTH<span class="key-hint">Space</span></div>' +
            '<div class="ctrl-btn" onclick="sendReset()">RESET<span class="key-hint">R</span></div>';
    }
}

// ========================
// Debug Controls
// ========================

function toggleBrain() {
    wsSend({ type: 'toggle_brain' });
}

function toggleVoice() {
    voiceEnabled = !voiceEnabled;
    if (!voiceEnabled && voiceManager) {
        voiceManager.stop();
    }
    wsSend({ type: 'toggle_voice' });
}

function toggleTestMode() {
    wsSend({ type: 'toggle_test_mode' });
}

function sendFullReset() {
    wsSend({ type: 'full_reset' });
    if (robotView) robotView.reset();
    // Clear command log
    var log = document.getElementById('command-log');
    if (log) { log.innerHTML = ''; logEntryCount = 0; }
    tickCount = 0;
}

function updateToggleButton(btnId, active) {
    var btn = document.getElementById(btnId);
    if (!btn) return;
    if (active) {
        btn.classList.add('active-toggle');
    } else {
        btn.classList.remove('active-toggle');
    }
    var hint = btn.querySelector('.key-hint');
    if (hint) hint.textContent = active ? 'On' : 'Off';
}

// ========================
// Brain Simulator
// ========================

function simulateBrain(classIndex) {
    wsSend({ type: 'simulate_brain', class_index: classIndex });
}

function updateSimBrainUI(activeClass) {
    document.querySelectorAll('.sim-btn').forEach(function(btn) {
        var cls = parseInt(btn.getAttribute('data-cls'));
        if (activeClass !== null && cls === activeClass) {
            btn.classList.add('sim-active');
        } else {
            btn.classList.remove('sim-active');
        }
    });
    var stopBtn = document.getElementById('btn-sim-stop');
    if (stopBtn) {
        if (activeClass !== null) {
            stopBtn.classList.add('sim-running');
        } else {
            stopBtn.classList.remove('sim-running');
        }
    }
}

// ========================
// Voice
// ========================

function toggleMic() {
    if (voiceManager) {
        voiceManager.toggle();
    }
}

function handleVoiceTranscript(text, confidence) {
    // Update UI
    const lastEl = document.getElementById('last-transcript-text');
    if (lastEl) lastEl.textContent = `"${text}"`;

    // Add to transcript list
    const list = document.getElementById('transcript-list');
    if (list) {
        const entry = document.createElement('div');
        entry.className = 'transcript-entry';
        entry.textContent = text;
        list.appendChild(entry);
        list.scrollTop = list.scrollHeight;

        // Trim
        while (list.children.length > 20) {
            list.removeChild(list.firstChild);
        }
    }

    // Send to backend only if voice is enabled
    if (!voiceEnabled) return;
    wsSend({
        type: 'voice_transcript',
        text: text,
        confidence: confidence,
        timestamp: Date.now() / 1000,
    });
}

// ========================
// Keyboard Controls
// ========================

const KEY_MAP_DIRECT = {
    'w': 'MOVE_FORWARD',
    'ArrowUp': 'MOVE_FORWARD',
    's': 'STOP',
    'ArrowDown': 'STOP',
    'a': 'ROTATE_LEFT',
    'ArrowLeft': 'ROTATE_LEFT',
    'd': 'ROTATE_RIGHT',
    'ArrowRight': 'ROTATE_RIGHT',
    'x': 'MOVE_BACKWARD',
    'e': 'GRAB',
    'q': 'RELEASE',
    'g': 'SHIFT_GEAR',
    ' ': 'BOTH_FISTS',
};

const KEY_MAP_BCI = {
    'w': 'BOTH_FISTS',        // Both Fists (gear-dependent)
    'ArrowUp': 'BOTH_FISTS',
    's': 'STOP',              // Relax → idle
    'ArrowDown': 'STOP',
    'a': 'ROTATE_LEFT',       // Left Fist
    'ArrowLeft': 'ROTATE_LEFT',
    'd': 'ROTATE_RIGHT',      // Right Fist
    'ArrowRight': 'ROTATE_RIGHT',
    'g': 'SHIFT_GEAR',        // Tongue Tapping
    ' ': 'BOTH_FISTS',
};

document.addEventListener('keydown', (e) => {
    // Don't capture if typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // Mode toggle
    if (e.key === 'm' || e.key === 'M') {
        e.preventDefault();
        toggleControlMode();
        return;
    }

    // Reset
    if (e.key === 'r') {
        e.preventDefault();
        sendReset();
        return;
    }

    var keyMap = controlMode === 'bci' ? KEY_MAP_BCI : KEY_MAP_DIRECT;

    if (e.key in keyMap) {
        e.preventDefault();
        sendCommand(keyMap[e.key]);
    }
});

// ========================
// Initialization
// ========================

// ========================
// Server Info / Footer
// ========================

function fetchServerInfo() {
    fetch('/api/server-info')
        .then(r => r.json())
        .then(info => {
            const footer = document.getElementById('deploy-footer');
            if (footer) {
                footer.textContent = `ThoughtLink v${info.version} — Edge Server: ${info.host}:${info.port} | Clients connected: ${info.clients_connected}`;
            }
        })
        .catch(() => {});
}

// ========================
// Initialization
// ========================

window.addEventListener('DOMContentLoaded', () => {
    // Initialize components
    eegChart = new EEGChart('eeg-canvas');
    robotView = new RobotView('robot-canvas');
    voiceManager = new VoiceManager(handleVoiceTranscript);

    // Set initial gear display
    updateGearDisplay('NEUTRAL');

    // Render manual controls for initial mode
    renderManualControls();

    // Connect WebSocket
    connectWebSocket();

    // Fetch server info for footer, refresh every 5s
    fetchServerInfo();
    setInterval(fetchServerInfo, 5000);

    console.log('[ThoughtLink] Dashboard initialized');
    addLogEntry('system', 'INIT', 'Dashboard initialized', Date.now() / 1000);
});
