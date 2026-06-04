"""RoboDK object-name helpers for boxes, lids and batteries.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from app_config import RACK_TO_NUMBER

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
