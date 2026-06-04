"""StationLogic EvaluationMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *


class EvaluationMixin:
    def make_signature(self, results: Dict[str, Any]) -> Tuple[Any, ...]:
        signature = []
        for slot_id in RACK_SLOT_IDS:
            slot = results.get(slot_id, {}) or {}
            batteries = slot.get("battery_slots", {}) or {}
            battery_signature = tuple(
                (
                    battery_id,
                    bool((batteries.get(battery_id, {}) or {}).get("battery_present", False)),
                    (batteries.get(battery_id, {}) or {}).get("battery_color", None),
                    (batteries.get(battery_id, {}) or {}).get("polarity_ok", None),
                )
                for battery_id in BATTERY_SLOT_IDS
            )
            signature.append(
                (
                    slot_id,
                    bool(slot.get("box_present", False)),
                    slot.get("box_state", "unknown"),
                    bool(slot.get("confirmed_open", False)),
                    slot.get("lid_color", None),
                    slot.get("open_box_color", None),
                    battery_signature,
                )
            )
        return tuple(signature)
    def update(self, results: Dict[str, Any]) -> None:
        if not results:
            return

        if self.cell_treatment_locked and self.frozen_active_slot_id is not None and self.frozen_active_slot_results is not None:
            results = deepcopy(results)
            results[self.frozen_active_slot_id] = deepcopy(self.frozen_active_slot_results)

        self.update_camera_memory(results)

        if self.paused and self.get_closed_box_with_lid_from_camera(results) is not None:
            self.paused = False
            print("[StationLogic] Nueva caja detectada. Saliendo de espera en PrepareLid.")

        if self.robot_safety_stop_active:
            return

        self.last_state_signature = self.make_signature(results)
        self.evaluate_station(results)
    def evaluate_station(self, results: Dict[str, Any]) -> None:
        now = time.time()
        if now - self.last_action_time < self.action_cooldown_s:
            return
        if self.paused:
            return
        if self.runtime_pause_active:
            return

        print("\n[StationLogic] Nuevo estado de cámara recibido")
        self.sync_finished_boxes_removed_from_camera(results)
        completed_boxes_before = self.completed_boxes_count
        pending_bridge_box = self.find_pending_bridge_box()

        if self.pending_lid_transfer is not None:
            did_action = self.resolve_pending_lid_transfer()
            self.last_action_time = time.time()
            return

        # Si hay una caja activa pero la cámara aún no la ve abierta, la liberamos
        # para que pueda atender nuevas cajas cerradas si fuese necesario.
        if self.active_box_slot is not None:
            active_state = results.get(rack_slot_id(self.active_box_slot), {}) or {}
            active_box = self.boxes[self.active_box_slot]
            if (
                active_box["state"] in ["open_waiting_cells", "processing_cells", "waiting_rack_cells"]
                and not active_state.get("confirmed_open", False)
            ):
                print(f"[Memory][AVISO] Libero active_box_slot={self.active_box_slot}; cámara no ve caja abierta.")
        did_action = False

        if pending_bridge_box is not None:
            self.active_box_slot = None
            did_action = self.buscar_bridge(pending_bridge_box, results)
            if self.bridge_complete(pending_bridge_box):
                self.try_close_completed_boxes()
            if self.completed_boxes_count > completed_boxes_before:
                if self.all_station_boxes_finished():
                    print("TODAS LAS CAJAS LISTAS")
                    self.move_final_home()
                    self.shutdown_requested = True
                    self.paused = True
                else:
                    self.move_to_prepare_lid_wait()
            self.last_action_time = time.time()
            return

        did_action |= self.try_close_completed_boxes()
        if self.stop_cycle_if_needed("cerrar cajas"):
            self.last_action_time = time.time()
            return

        if self.active_box_slot is not None:
            active_box = self.boxes.get(self.active_box_slot, {})
            if active_box.get("state") not in ["open_waiting_cells", "processing_cells", "waiting_rack_cells"]:
                self.active_box_slot = None

        if self.active_box_slot is None:
            for slot in [1, 2, 3]:
                box = self.boxes[slot]
                slot_state = results.get(rack_slot_id(slot), {}) or {}
                if (
                    box["present"]
                    and box["lid_collected"]
                    and box["state"] in ["open_waiting_cells", "processing_cells", "waiting_rack_cells"]
                    and slot_state.get("confirmed_open", False)
                ):
                    self.active_box_slot = slot
                    break

        if self.active_box_slot is not None:
            before_complete = self.box_complete(self.active_box_slot)
            action_cells = self.process_active_box_cells(results)
            after_complete = self.box_complete(self.active_box_slot) if self.active_box_slot else False
            did_action = did_action or action_cells or (after_complete and not before_complete)

            if self.stop_cycle_if_needed("procesar celdas"):
                self.last_action_time = time.time()
                return

            if self.find_pending_bridge_box() is not None:
                self.active_box_slot = None
                self.last_action_time = time.time()
                return

            if after_complete and self.active_box_slot is not None:
                self.try_close_completed_boxes()
                self.active_box_slot = None
            elif not action_cells:
                if self.boxes[self.active_box_slot]["state"] == "waiting_rack_cells":
                    self.active_box_slot = None
                self.move_to_pick_cell_wait()

        if not did_action and self.active_box_slot is None:
            did_action = self.process_first_closed_box_with_lid(results)
            if self.stop_cycle_if_needed("procesar tapa nueva"):
                self.last_action_time = time.time()
                return

        if self.active_box_slot is None:
            did_action |= self.try_fill_pending_boxes_from_rack(results)
            if self.stop_cycle_if_needed("rellenar pendientes"):
                self.last_action_time = time.time()
                return

        if did_action:
            self.try_close_completed_boxes()
            if self.stop_cycle_if_needed("cierre final"):
                self.last_action_time = time.time()
                return
            if self.completed_boxes_count > completed_boxes_before:
                if self.all_station_boxes_finished():
                    print("TODAS LAS CAJAS LISTAS")
                    self.move_final_home()
                    self.shutdown_requested = True
                    self.paused = True
                    self.last_action_time = time.time()
                    return
                else:
                    self.move_to_prepare_lid_wait()

        if not did_action:
            self.maybe_pause_when_all_done(results)

        self.last_action_time = time.time()
