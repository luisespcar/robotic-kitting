"""StationLogic constants and RoboDK imports."""

from __future__ import annotations

import socket
import time
from math import radians
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from robodk.robolink import (
        ITEM_TYPE_FRAME,
        ITEM_TYPE_PROGRAM,
        ITEM_TYPE_TARGET,
        RUNMODE_RUN_ROBOT,
        RUNMODE_SIMULATE,
        Robolink,
    )
    from robodk.robomath import Pose_2_TxyzRxyz, TxyzRxyz_2_Pose, rotx, roty, rotz, transl
except ImportError:
    from robolink import (
        ITEM_TYPE_FRAME,
        ITEM_TYPE_PROGRAM,
        ITEM_TYPE_TARGET,
        RUNMODE_RUN_ROBOT,
        RUNMODE_SIMULATE,
        Robolink,
    )
    from robomath import Pose_2_TxyzRxyz, TxyzRxyz_2_Pose, rotx, roty, rotz, transl


# =========================================================
# CONFIGURACIÓN LÓGICA
# =========================================================

RACK_SLOT_IDS = ["rack_slot_1", "rack_slot_2", "rack_slot_3"]
BATTERY_SLOT_IDS = ["battery_slot_1", "battery_slot_2", "battery_slot_3", "battery_slot_4"]

RACK_SLOT_TO_NUM = {"rack_slot_1": 1, "rack_slot_2": 2, "rack_slot_3": 3}
VALID_COLORS = {"red", "green", "blue"}

BRIDGE_REQUIRED_TYPES = ("small", "large")
BRIDGE_TARGET_BY_TYPE = {"small": "Small", "large": "Large"}
BRIDGE_TARGET_DOWN_BY_TYPE = {"small": "Smalld", "large": "Larged"}
BRIDGE_PICK_TARGET_BY_TYPE = {"small": "BridgeSmallPick", "large": "BridgeLargePick"}
BRIDGE_APPROACH_TARGET_BY_TYPE = {"small": "BridgeSmallApproach", "large": "BridgeLargeApproach"}
BRIDGE_FRAME_NAME = "Bridge"
BRIDGE_PREPARE_TARGET = "PrepareBridge"
BRIDGE_SCAN_TARGET = BRIDGE_PREPARE_TARGET
BRIDGE_SOURCE_UP_TARGET = "bridge"
BRIDGE_SOURCE_DOWN_TARGET = "down"
BRIDGE_ROTATION_AXIS = "Z"
BRIDGE_ROTATION_SIGN = 1.0
BRIDGE_ROTATION_OFFSET_DEG = -90
CELL_PLACE_DOWN_Z_OFFSET_MM = 2.0
LID_CLOSE_FINAL_DOWN_OFFSET_MM = -10.0
LID_STORE_FINAL_DOWN_OFFSET_MM = -7.0

RACK_CELLS_BY_COLOR = {
    "red": [4, 3, 2, 1],
    "green": [5, 6, 7, 8],
    "blue": [9, 10, 11, 12],
}

RACK_CELL_EXPECTED_COLOR = {
    slot: color
    for color, slots in RACK_CELLS_BY_COLOR.items()
    for slot in slots
}

# Tapas:
# Ajusta esto si en tu RoboDK los huecos físicos están en otro orden.
LID_SLOT_BY_COLOR = {"red": 1, "blue": 2, "green": 3}
LID_SLOT_EXPECTED_COLOR = {slot: color for color, slot in LID_SLOT_BY_COLOR.items()}


# =========================================================
# NOMBRES ROBO DK
# =========================================================

REQUIRED_TARGET_NAMES = [
    "Home", "HomeUR10", "PrepareLid", "PrepareBridge", "PlaceCell",
    "pos", "go", "up", "out",
    "lidpos", "lidgo", "lidup", "liddown", "lidout",
    "C1", "C2", "C3", "C4",
    "C1d", "C2d", "C3d", "C4d",
    "C1Inv", "C2Inv", "C3Inv", "C4Inv",
    "C1dInv", "C2dInv", "C3dInv", "C4dInv",
    "Lid", "Lidd", "LidPick", "Larged", "Large", "Small", "Smalld",
]

REQUIRED_FRAME_NAMES = (
    ["Lid1", "Lid2", "Lid3"]
    + [f"cell{i}" for i in range(1, 13)]
    + ["Box1", "Box2", "Box3", "Bridge"]
)

GRIPPER_ROBODK_PROGRAMS = ["OpenGripper", "CloseGripper", "OpenCell", "CloseCell", "OpenLid", "CloseLid", "OutLid", "bridgeopen", "CloseBridge", "AttachLidRed", "AttachLidBlue", "AttachLidGreen",]

OPTIONAL_PLACE_CELL_TARGET = "PlaceCell"

CONNECTION_ERROR_KEYWORDS = (
    "connection", "connect", "disconnect", "not connected", "refused",
    "timed out", "timeout", "broken pipe", "protective", "emergency",
    "power", "current", "robot stopped", "stopped", "safety",
)

GRIPPER_RECONNECT_RETRIES = 12
GRIPPER_RECONNECT_DELAY_S = 0.75
GRIPPER_PROGRAM_SETTLE_S = 3.0
BRIDGE_GRIPPER_EXTRA_SETTLE_S = 0.5
BRIDGE_GRIPPER_URP_NAMES = {"bridgeopen", "gripperclosebridge"}

ROBOT_CONNECT_RETRIES = 6
ROBOT_CONNECT_RETRY_DELAY_S = 0.75
OPEN_BOX_VISION_CONFIRMATION_S = 2.0
LID_POST_PICK_ANALYZE_S = 1.0
