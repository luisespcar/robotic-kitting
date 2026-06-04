"""Small pure helpers used by StationLogic.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List

from station_config import *

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rack_slot_id(slot_num: int) -> str:
    return f"rack_slot_{slot_num}"


def battery_slot_id(cell_num: int) -> str:
    return f"battery_slot_{cell_num}"


def missing_visible_battery_slots(slot_state: Dict[str, Any]) -> List[str]:
    """Return box cell slots that vision has not detected as occupied yet."""
    batteries = (slot_state or {}).get("battery_slots", {}) or {}
    return [
        battery_id
        for battery_id in BATTERY_SLOT_IDS
        if not bool((batteries.get(battery_id, {}) or {}).get("battery_present", False))
    ]


def physical_cell_id_from_box_position(box_slot: int, cell_num: int) -> str:
    """ID físico base de la celda según la posición original de cámara.

    Box1 C1..C4 -> S01..S04
    Box2 C1..C4 -> S05..S08
    Box3 C1..C4 -> S09..S12

    Importante: este ID representa la pieza física, no el hueco actual.
    Si S10 se mueve de Box3C2 a cell9 y luego a Box1C4, sigue siendo S10.
    """
    if box_slot not in [1, 2, 3]:
        raise ValueError(f"box_slot inválido: {box_slot}")
    if cell_num not in [1, 2, 3, 4]:
        raise ValueError(f"cell_num inválido: {cell_num}")
    global_idx = (box_slot - 1) * 4 + cell_num
    return f"S{global_idx:02d}"


def empty_box_state() -> Dict[str, Any]:
    return {
        "present": False,
        "color": None,
        "state": "empty",
        "lid_collected": False,
        "lid_visual_name": None,
        "cells_locked": False,
        "initial_cells_captured": False,
        "awaiting_direct_open_capture": False,
        "cells": [None, None, None, None],
        "bridge_parts_done": {piece_type: False for piece_type in BRIDGE_REQUIRED_TYPES},
        "bridge_parts_info": {},
        "detected_at": None,
        "finished_at": None,
    }
