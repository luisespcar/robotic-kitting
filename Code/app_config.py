"""Runtime configuration for the modular vision application.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from pathlib import Path

import cv2

MODULE_DIR = Path(__file__).resolve().parent
BASE_DIR = MODULE_DIR
MODEL_DIR = MODULE_DIR / "model"
CONFIG_DIR = MODULE_DIR / "config"

MODEL_PATH = MODEL_DIR / "best.pt"
BRIDGE_MODEL_PATH = MODEL_DIR / "best_brigde.pt"
HAND_LANDMARKER_PATH = MODEL_DIR / "hand_landmarker.task"
ROIS_JSON_PATH = CONFIG_DIR / "yolo_logic_rois_updated.json"
CALIBRATION_JSON_PATH = CONFIG_DIR / "camera_calibration.json"
BRIDGE_HOMOGRAPHY_JSON_PATH = CONFIG_DIR / "homography.json"
OUTPUT_FOLDER = BASE_DIR / "tests"

# Cámara externa en tiempo real
CAMERA_INDEX = 0
AUTO_DETECT_CAMERA = False
CAMERA_SEARCH_INDEXES = [0, 1, 2, 3]
CAMERA_BACKEND = cv2.CAP_DSHOW
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
CAMERA_FPS = 30
MAX_CAMERA_READ_FAILS_BEFORE_REOPEN = 10
CAMERA_REOPEN_DELAY_S = 0.5

# YOLO
CONFIDENCE = 0.25
ROBODK_MIN_CONFIDENCE = 0.80
IMG_SIZE = 1024
DEVICE = 0          # Usa 0 si CUDA funciona. Usa "cpu" si no.
UNDISTORT_ALPHA = 0

# Mano (Google MediaPipe)
# Cargar siempre el landmarker para registrar presencia en la logica de tapas.
ENABLE_HAND_LANDMARKER = True
HAND_MAX_NUM_HANDS = 1
HAND_MIN_DETECTION_CONFIDENCE = 0.5
HAND_MIN_PRESENCE_CONFIDENCE = 0.5
HAND_MIN_TRACKING_CONFIDENCE = 0.5
HAND_SAFETY_CONFIDENCE_THRESHOLD = 0.80

# Visualización
SHOW_WINDOW = True
SHOW_CAMERA_BEFORE_ROBODK_INIT = True
SAVE_OUTPUT_VIDEO = False
OUTPUT_VIDEO_PATH = OUTPUT_FOLDER / "vision_logic_stationlogic_only.mp4"
PRINT_STATE_EVERY_N_FRAMES = 0
DISPLAY_PROCESSED_FRAME = False
DRAW_LIVE_VISION_OVERLAYS = True

# RoboDK / Máquina de estados
ENABLE_ROBODK_LIVE_UPDATE = True
ENABLE_STATION_LOGIC = True
ASYNC_ROBODK_INIT = True
STATION_SIMULATION_MODE = False
STATION_DRY_RUN = False
MOVE_HOME_ON_START = True
VISION_SETTLE_AFTER_ROBOT_ACTION_S = 0.0
RUN_REPLACE_ALL_ON_START = True
REPLACE_ALL_PROGRAM_NAME = "Replace All"

# Velocidad robot
ROBOT_SPEED_PERCENT_DEFAULT = 50.0
ROBOT_STARTUP_HOME_SPEED_PERCENT = ROBOT_SPEED_PERCENT_DEFAULT
ROBOT_SPEED_PERCENT_MIN = 0.0
ROBOT_SPEED_PERCENT_MAX = 100.0
ROBOT_SPEED_PERCENT_STEP = 10.0
ROBOT_LINEAR_SPEED_MAX_MM_S = 200.0
ROBOT_JOINT_SPEED_MAX_DEG_S = 80.0
ROBOT_LINEAR_ACCEL_MAX_MM_S2 = 300.0
ROBOT_JOINT_ACCEL_MAX_DEG_S2 = 120.0


POLARITY_ROTATION_AXIS = "X"

RACK_SLOT_IDS = ["rack_slot_1", "rack_slot_2", "rack_slot_3"]
BATTERY_SLOT_IDS = ["battery_slot_1", "battery_slot_2", "battery_slot_3", "battery_slot_4"]
RACK_TO_NUMBER = {"rack_slot_1": 1, "rack_slot_2": 2, "rack_slot_3": 3}

LID_OBJECTS = {
    "rack_slot_1": {"red": "RedLid1", "green": "GreenLid1", "blue": "BlueLid1"},
    "rack_slot_2": {"red": "RedLid2", "green": "GreenLid2", "blue": "BlueLid2"},
    "rack_slot_3": {"red": "RedLid3", "green": "GreenLid3", "blue": "BlueLid3"},
}

# Pose absoluta en RoboDK para simular que la tapa cae por gravedad al soltarla
# encima de cada caja. Se aplica solo como movimiento visual del objeto lid.
LID_GRAVITY_DROP_GLOBAL_POSES = {
    1: {"x": 1995.874146, "y": 1055.367188, "z": 455.950357, "rz_deg": 90.0},
    2: {"x": 1818.874146, "y": 1055.367188, "z": 455.950357, "rz_deg": 90.0},
    3: {"x": 1641.874146, "y": 1055.367188, "z": 455.950357, "rz_deg": 90.0},
}

BOX_OBJECTS = {
    "rack_slot_1": {"red": "RedBox1", "green": "GreenBox1", "blue": "BlueBox1"},
    "rack_slot_2": {"red": "RedBox2", "green": "GreenBox2", "blue": "BlueBox2"},
    "rack_slot_3": {"red": "RedBox3", "green": "GreenBox3", "blue": "BlueBox3"},
}


def battery_base_index(slot_id, battery_slot_id):
    rack_num = RACK_TO_NUMBER[slot_id]
    battery_num = int(battery_slot_id.split("_")[-1])
    global_idx = (rack_num - 1) * 4 + battery_num
    return f"S{global_idx:02d}"


def battery_object_names(slot_id, battery_slot_id):
    base = battery_base_index(slot_id, battery_slot_id)
    return {
        "base": base,
        "red": f"{base}_red",
        "green": f"{base}_green",
        "blue": f"{base}_blue",
    }


# =========================================================
# CLASES DEL MODELO YOLO
# =========================================================

BOX_CLASSES = ["box_blue", "box_green", "box_red"]
LID_CLASSES = ["lid_blue", "lid_green", "lid_red"]
BATTERY_CLASSES = ["battery_blue", "battery_green", "battery_red"]
TERMINAL_CLASSES = ["terminal_red"]
BRIDGE_CLASSES = ["small", "large"]
BRIDGE_CONFIDENCE = 0.08
BRIDGE_IOU = 0.95
BRIDGE_MAX_DET = 50
BRIDGE_MIN_MASK_AREA = 80
BRIDGE_PICK_APPROACH_OFFSET_MM = 100.0
BRIDGE_ANGLE_OFFSET_DEG = 0.0
BRIDGE_STABILIZER_DISTANCE_THRESHOLD = 50
BRIDGE_STABILIZER_ALPHA = 0.7
BRIDGE_DEBUG_PRINT_EVERY_N_FRAMES = 0
BRIDGE_HOMOGRAPHY_PRINT_EVERY_N_FRAMES = 0
BRIDGE_LIVE_VISUAL_MATCH_THRESHOLD_MM = 70.0
BRIDGE_LIVE_VISUAL_MOVE_THRESHOLD_MM = 8.0
BRIDGE_LIVE_VISUAL_ANGLE_THRESHOLD_DEG = 6.0
BRIDGE_LIVE_VISUAL_MISSING_FRAMES_TO_HIDE = 2
BRIDGE_VISUAL_OBJECTS = {
    1: {"small": "small_1", "large": "large_1"},
    2: {"small": "small_2", "large": "large_2"},
    3: {"small": "small_3", "large": "large_3"},
}
BRIDGE_FRAME_NAME = "Bridge"
BRIDGE_PICK_TARGET_BY_TYPE = {"small": "BridgeSmallPick", "large": "BridgeLargePick"}
BRIDGE_APPROACH_TARGET_BY_TYPE = {"small": "BridgeSmallApproach", "large": "BridgeLargeApproach"}
BRIDGE_TARGET_DOWN_BY_TYPE = {"small": "Smalld", "large": "Larged"}
BRIDGE_VISUAL_FRAME_NAME = "bridgeopen"
BRIDGE_VISUAL_SOURCE_TARGET = "bridgeopen"
BRIDGE_VISUAL_ROTATION_AXIS = "Z"
BRIDGE_VISUAL_ROTATION_SIGN = 1.0
BRIDGE_VISUAL_ROTATION_OFFSET_DEG = -90.0
LID_VISUAL_BOX_GLOBAL_Z_OFFSET_MM = -10.0
