"""Keeps completed/locked slots visually stable across noisy camera frames.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from copy import deepcopy

from app_config import *

class FinalSlotLockManager:
    OPEN_MEMORY_STATES = {
        "open_waiting_cells",
        "processing_cells",
        "waiting_rack_cells",
        "bridges_pending",
        "bridge_ready",
    }
    FINAL_MEMORY_STATES = {"closed_complete", "finished"}

    def __init__(self):
        self.station_logic = None
        self.slot_memory = {
            slot_id: {
                "was_open": False,
                "locked": False,
                "lock_announced": False,
                "unlock_announced": False,
                "snapshot": None,
            }
            for slot_id in RACK_SLOT_IDS
        }

    def bind_station_logic(self, station_logic):
        self.station_logic = station_logic

    def station_box_state(self, slot_id):
        if self.station_logic is None:
            return None
        boxes = getattr(self.station_logic, "boxes", {}) or {}
        slot_num = RACK_TO_NUMBER.get(slot_id)
        box = boxes.get(slot_num, {}) or {}
        if isinstance(box, dict):
            return box.get("state")
        return None

    def station_box_color(self, slot_id):
        if self.station_logic is None:
            return None
        boxes = getattr(self.station_logic, "boxes", {}) or {}
        slot_num = RACK_TO_NUMBER.get(slot_id)
        box = boxes.get(slot_num, {}) or {}
        if isinstance(box, dict):
            return box.get("color")
        return None

    def station_lid_color(self, slot_id):
        if self.station_logic is None:
            return None
        boxes = getattr(self.station_logic, "boxes", {}) or {}
        slot_num = RACK_TO_NUMBER.get(slot_id)
        box = boxes.get(slot_num, {}) or {}
        if isinstance(box, dict):
            return box.get("detected_lid_color")
        return None

    @staticmethod
    def _is_valid_color(color):
        return color in {"red", "green", "blue"}

    def _build_locked_snapshot(self, slot_id, slot_state):
        slot_state = dict(slot_state or {})
        lid_color = (
            slot_state.get("lid_color")
            or self.station_lid_color(slot_id)
            or self.station_box_color(slot_id)
            or slot_state.get("open_box_color")
        )
        if not self._is_valid_color(lid_color):
            lid_color = None

        battery_slots = {}
        for battery_slot_id in BATTERY_SLOT_IDS:
            battery_slots[battery_slot_id] = {
                "battery_present": False,
                "battery_color": None,
                "polarity_ok": None,
            }

        return {
            "box_present": True,
            "box_state": "closed",
            "confirmed_open": False,
            "lid_color": lid_color,
            "closed_box_color": self.station_box_color(slot_id) or lid_color,
            "open_box_color": None,
            "box_detected": bool(slot_state.get("box_detected", False)),
            "lid_detected": True,
            "detected_box_color": None,
            "battery_slots": battery_slots,
            "slot_locked_final": True,
        }

    def _lock_slot(self, slot_id, slot_state, reason):
        memory = self.slot_memory[slot_id]
        if memory["locked"]:
            return
        memory["locked"] = True
        memory["snapshot"] = self._build_locked_snapshot(slot_id, slot_state)
        if not memory["lock_announced"]:
            memory["lock_announced"] = True
            print(f"[SlotLock] {slot_id} bloqueado definitivamente: {reason}")

    def _unlock_slot(self, slot_id, reason):
        memory = self.slot_memory[slot_id]
        if not memory["locked"]:
            return
        memory["locked"] = False
        memory["snapshot"] = None
        if not memory["unlock_announced"]:
            memory["unlock_announced"] = True
            print(f"[SlotLock] {slot_id} desbloqueado: {reason}")

    def apply(self, results):
        filtered_results = dict(results or {})

        for slot_id in RACK_SLOT_IDS:
            slot_state = dict(filtered_results.get(slot_id, {}) or {})
            memory = self.slot_memory[slot_id]
            station_state = self.station_box_state(slot_id)

            camera_says_open = (
                bool(slot_state.get("confirmed_open", False))
                or slot_state.get("box_state") == "open"
                or self._is_valid_color(slot_state.get("open_box_color"))
            )
            memory_says_open = station_state in self.OPEN_MEMORY_STATES
            if camera_says_open or memory_says_open:
                if memory["locked"]:
                    self._unlock_slot(slot_id, "vision/memoria ve caja abierta de nuevo")
                memory["was_open"] = True

            if not memory["locked"]:
                final_by_station = station_state in self.FINAL_MEMORY_STATES
                final_by_camera = (
                    memory["was_open"]
                    and slot_state.get("box_state") == "closed"
                    and self._is_valid_color(slot_state.get("lid_color"))
                )
                if final_by_station:
                    self._lock_slot(slot_id, slot_state, f"state_machine={station_state}")
                elif final_by_camera:
                    self._lock_slot(slot_id, slot_state, "camara vio caja abierta y luego cerrada con tapa")

            if memory["locked"] and memory["snapshot"] is not None:
                filtered_results[slot_id] = dict(memory["snapshot"])
            else:
                filtered_results[slot_id] = slot_state

        return filtered_results
