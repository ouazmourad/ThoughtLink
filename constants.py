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
TRAINING_DIR = PROJECT_ROOT / "training"
CHECKPOINT_DIR = TRAINING_DIR / "checkpoints"
RESULTS_DIR = TRAINING_DIR / "results"

# Ensure output directories exist
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

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

# === Factory Robot Constants ===
FACTORY_WAYPOINTS = {
    "Shelf A": (-3.5, -2.0),
    "Shelf B": (3.5, -2.0),
    "Conveyor": (0.0, -3.5),
    "Table": (2.0, 1.5),
    "Pallet 1": (-1.5, 1.0),
    "Pallet 2": (1.5, 1.0),
}
FACTORY_WAYPOINT_ORDER = ["Shelf A", "Shelf B", "Conveyor", "Table", "Pallet 1", "Pallet 2"]
FACTORY_PATROL_ROUTE = ["Pallet 1", "Shelf A", "Conveyor", "Shelf B", "Table", "Pallet 2"]

# Grabbable / pushable box geom names
FACTORY_GRABBABLE_BOXES = [
    "conv_box1", "conv_box2", "conv_box3",
    "p1_box1", "p1_box2", "p1_box3",
    "table_box1", "table_box2",
]
FACTORY_PUSHABLE_BOXES = ["conv_box1", "conv_box2", "conv_box3"]

# Safety thresholds (meters / radians / seconds)
OBSTACLE_WARNING_DIST = 1.5
OBSTACLE_DANGER_DIST = 0.6
GRAB_REACH_DIST = 1.0
WAYPOINT_ARRIVAL_DIST = 0.5
WAYPOINT_ALIGN_THRESHOLD = 0.3
ESTOP_HOLD_SECONDS = 2.0
TRAIL_MIN_DISTANCE = 0.3
NUM_TRAIL_DOTS = 100

# Geofence zones: name -> (min_x, max_x, min_y, max_y)
FACTORY_GEOFENCE_ZONES = {
    "Back Wall": (-8, 8, -6.5, -5.5),
}

# Obstacle geom names for proximity checking
FACTORY_OBSTACLE_GEOMS = [
    "pillar_1", "pillar_2",
    "bollard_1", "bollard_2", "bollard_3", "bollard_4",
    "sA_upright_FL", "sA_upright_FR",
    "sB_upright_FL", "sB_upright_FR",
]

# Status light colors: action -> [r, g, b, a]
STATUS_COLORS = {
    "FORWARD": [0.0, 0.9, 0.0, 0.8],
    "LEFT":    [0.0, 0.4, 1.0, 0.8],
    "RIGHT":   [1.0, 0.0, 0.0, 0.8],
    "STOP":    [1.0, 0.9, 0.0, 0.8],
    "GRAB":    [0.7, 0.0, 1.0, 0.8],
}
