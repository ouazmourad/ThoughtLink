"""
ThoughtLink — Shared Constants
All modules import from here. Single source of truth.
"""

import os
from pathlib import Path

# === Project Paths ===
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = Path(os.environ.get(
    "THOUGHTLINK_DATA_DIR",
    str(Path.home() / "robot_control" / "data"),
))
CHECKPOINT_DIR = PROJECT_ROOT / "training" / "checkpoints"
RESULTS_DIR = PROJECT_ROOT / "training" / "results"

# === Label Mapping (handles dataset typos) ===
LABEL_MAP = {
    "Right Fist": 0,
    "Left First": 1,   # typo in dataset
    "Left Fist": 1,    # correct spelling
    "Both Firsts": 2,  # typo in dataset
    "Both Fists": 2,   # correct spelling
    "Tongue Tapping": 3,
    "Relax": 4,
}

LABEL_MAP_BINARY = {
    "Right Fist": 0,
    "Left First": 1,
    "Left Fist": 1,
}

LABEL_NAMES = ["Right Fist", "Left Fist", "Both Fists", "Tongue Tapping", "Relax"]
LABEL_NAMES_BINARY = ["Right Fist", "Left Fist"]
NUM_CLASSES = 5
NUM_CLASSES_BINARY = 2

# === Brain Label → Robot Command ===
# Maps class index to bri.Action name
BRAIN_LABEL_TO_COMMAND = {
    0: "RIGHT",       # Right Fist → turn right
    1: "LEFT",        # Left Fist → turn left
    2: "STOP",        # Both Fists → halt
    3: "FORWARD",     # Tongue Tapping → walk forward
    4: "STOP",        # Relax → stand still
}

# === EEG Constants ===
EEG_SAMPLE_RATE = 500          # Hz
EEG_NUM_CHANNELS = 6
EEG_CHANNEL_NAMES = ["AFF6", "AFp2", "AFp1", "AFF5", "FCz", "CPz"]
CHUNK_DURATION_SECONDS = 15
CHUNK_TOTAL_SAMPLES = 7499     # 15s at 500Hz

# Windowing
WINDOW_SIZE_SAMPLES = 500      # 1 second window
WINDOW_STRIDE_SAMPLES = 125    # 0.25 second stride
STIMULUS_START_SAMPLE = 1500   # t=3s (rest period ends, stimulus begins)
MIN_DURATION_SECONDS = 2.0     # skip trials shorter than this

# === TD-NIRS Constants ===
NIRS_SAMPLE_RATE = 4.76        # Hz
NIRS_NUM_MODULES = 40
NIRS_NUM_SDS_RANGES = 3
NIRS_NUM_WAVELENGTHS = 2
NIRS_NUM_MOMENTS = 3

# === Inference Constants ===
CONFIDENCE_THRESHOLD = 0.7
SMOOTHING_WINDOW = 5           # majority vote buffer size
HYSTERESIS_COUNT = 3           # consecutive same-class required to switch

# === Training Constants ===
TRAIN_SUBJECTS = 14
VAL_SUBJECTS = 3
TEST_SUBJECTS = 3
SPLIT_SEED = 42
BATCH_SIZE = 64
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
NUM_EPOCHS = 50

# === Preprocessing Constants ===
BANDPASS_LOW = 1.0             # Hz
BANDPASS_HIGH = 40.0           # Hz
FILTER_ORDER = 4               # Butterworth filter order
