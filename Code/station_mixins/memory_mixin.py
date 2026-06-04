"""StationLogic MemoryMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *


class MemoryMixin:
    def reset_runtime_memory(self) -> None:
        self.boxes = {slot: empty_box_state() for slot in [1, 2, 3]}
        self.rack_cells = {
            slot: {"expected_color": RACK_CELL_EXPECTED_COLOR[slot], "cell": None}
            for slot in range(1, 13)
        }
        self.lid_slots = {
            slot: {"expected_color": LID_SLOT_EXPECTED_COLOR[slot], "stored": None}
            for slot in range(1, 4)
        }
        # Lids currently held by the robot (max 3). Each entry is a dict with
        # keys: id, color, source, picked_at
        self.picked_lids = []
        self.last_stored_lid: Optional[Dict[str, Any]] = None
        self.active_box_slot: Optional[int] = None
        self.pending_lid_transfer: Optional[Dict[str, Any]] = None
        self.completed_boxes_count = 0
        self.paused = False
        self.bridge_scan_active = False
        self.bridge_scan_box_slot: Optional[int] = None
        self.bridge_scan_requested_at: Optional[str] = None
        print("[Memory] Memoria RAM inicializada. No se lee ni escribe JSON externo.")
    def reset_open_box_confirmation(self) -> None:
        self.open_box_confirmation_slot = None
        self.open_box_confirmation_signature = None
        self.open_box_confirmation_since = 0.0
    def load_memory(self) -> Dict[str, Any]:
        self.reset_runtime_memory()
        return self.get_memory_snapshot()
    def save_memory(self, reason: str = "manual") -> None:
        # Intencionadamente vacío: no hay memoria externa.
        return None
    def get_memory_snapshot(self) -> Dict[str, Any]:
        return {
            "created_at": now_iso(),
            "mode": "RAM_ONLY",
            "safety": {
                "robot_safety_stop_active": self.robot_safety_stop_active,
                "requires_human_ack": self.robot_requires_human_ack,
                "last_error": self.robot_last_error,
                "last_error_context": self.robot_last_error_context,
            },
            "station": {
                "active_box_slot": self.active_box_slot,
                "paused": self.paused,
                "completed_boxes_count": self.completed_boxes_count,
                "boxes": deepcopy(self.boxes),
                "rack_cells": deepcopy(self.rack_cells),
                "lid_slots": deepcopy(self.lid_slots),
            },
            "last_camera_summary": deepcopy(self.last_camera_summary),
        }
    def update_camera_memory(self, results: Dict[str, Any], hand_state: Optional[Dict[str, Any]] = None) -> None:
        self.last_camera_results = deepcopy(results or {})
        self.last_camera_summary = self.compact_camera_summary(self.last_camera_results)
        # Guardar estado de mano para que la lógica pueda tomar decisiones de espera
        try:
            self.last_hand_state = deepcopy(hand_state or {})
        except Exception:
            self.last_hand_state = {}
    def should_scan_bridge_vision(self) -> bool:
        return bool(self.bridge_scan_active and self.bridge_scan_box_slot in [1, 2, 3])
    def activate_bridge_scan(self, box_slot: int) -> None:
        self.bridge_scan_active = True
        self.bridge_scan_box_slot = box_slot
        self.bridge_scan_requested_at = now_iso()
        print(f"[Bridge] Box{box_slot}: vision bridge activada en Home.")
    def deactivate_bridge_scan(self) -> None:
        if self.bridge_scan_active:
            print(f"[Bridge] Vision bridge desactivada.")
        self.bridge_scan_active = False
        self.bridge_scan_box_slot = None
        self.bridge_scan_requested_at = None
    def active_box_state_for_treatment(self) -> Optional[str]:
        if self.active_box_slot is None:
            return None
        box = (self.boxes.get(self.active_box_slot, {}) or {})
        return box.get("state")
    def set_cell_treatment_lock(self, locked: bool, results: Optional[Dict[str, Any]] = None) -> None:
        locked = bool(locked)
        treatable_states = {"open_waiting_cells", "processing_cells", "waiting_rack_cells"}

        if not locked:
            if self.cell_treatment_locked:
                print("[StationLogic] Desbloqueando memoria de caja activa.")
            self.cell_treatment_locked = False
            self.frozen_active_slot_id = None
            self.frozen_active_slot_results = None
            return

        if self.active_box_slot is None:
            return

        if self.active_box_state_for_treatment() not in treatable_states:
            return

        slot_id = rack_slot_id(self.active_box_slot)
        slot_state = deepcopy((results or {}).get(slot_id, {}) or {})
        if not slot_state:
            return

        if self.cell_treatment_locked and self.frozen_active_slot_id == slot_id:
            return

        self.cell_treatment_locked = True
        self.frozen_active_slot_id = slot_id
        self.frozen_active_slot_results = slot_state
        print(f"[StationLogic] Congelando memoria visual de {slot_id} para tratar celdas.")
    @staticmethod
    def compact_camera_summary(results: Dict[str, Any]) -> Dict[str, Any]:
        summary = {}
        for slot_id in RACK_SLOT_IDS:
            slot = results.get(slot_id, {}) or {}
            batteries = slot.get("battery_slots", {}) or {}
            summary[slot_id] = {
                "box_present": bool(slot.get("box_present", False)),
                "box_state": slot.get("box_state", "unknown"),
                "confirmed_open": bool(slot.get("confirmed_open", False)),
                "lid_color": slot.get("lid_color", None),
                "open_box_color": slot.get("open_box_color", None),
                "battery_slots": {
                    b_id: {
                        "battery_present": bool((batteries.get(b_id, {}) or {}).get("battery_present", False)),
                        "battery_color": (batteries.get(b_id, {}) or {}).get("battery_color", None),
                        "polarity_ok": (batteries.get(b_id, {}) or {}).get("polarity_ok", None),
                    }
                    for b_id in BATTERY_SLOT_IDS
                },
            }
        return summary
