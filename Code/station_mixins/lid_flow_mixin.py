"""StationLogic LidFlowMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from app_config import LID_OBJECTS
from station_config import *
from station_helpers import *


class LidFlowMixin:
    def store_lid(self, color: str, extra: Optional[Dict[str, Any]] = None) -> None:
        # Guardar un objeto completo en la ranura de tapa (no sólo color).
        slot = LID_SLOT_BY_COLOR[color]
        lid_obj = deepcopy(extra or {})
        lid_obj.setdefault("id", f"LID_{color}_{now_iso()}")
        lid_obj["color"] = color
        lid_obj.setdefault("location", f"Lid{slot}")
        lid_obj.setdefault("stored_at", now_iso())
        # Asociar el nombre visual que representa esa ranura de rack en RoboDK
        try:
            visual = LID_OBJECTS.get(f"rack_slot_{slot}", {}) or {}
            lid_obj.setdefault("visual_name", visual.get(color))
        except Exception:
            pass
        self.lid_slots[slot]["stored"] = lid_obj

    def remove_lid(self, color: str) -> None:
        slot = LID_SLOT_BY_COLOR[color]
        self.lid_slots[slot]["stored"] = None

    def lid_available(self, color: str) -> bool:
        if color not in VALID_COLORS:
            return False
        slot = LID_SLOT_BY_COLOR[color]
        stored = self.lid_slots[slot].get("stored")
        return isinstance(stored, dict) and stored.get("color") == color
    def find_free_rack_cell_slot(self, color: Optional[str]) -> Optional[int]:
        if color not in VALID_COLORS:
            return None
        for slot in RACK_CELLS_BY_COLOR[color]:
            if self.rack_cells[slot]["cell"] is None:
                return slot
        return None
    def store_cell_in_rack(self, slot: int, color: str, extra: Optional[Dict[str, Any]] = None) -> bool:
        if RACK_CELL_EXPECTED_COLOR.get(slot) != color:
            print(f"[Rack][AVISO] No guardo {color} en cell{slot}; esperado {RACK_CELL_EXPECTED_COLOR.get(slot)}")
            return False

        # Guardamos la PIEZA física completa, no solo el color.
        # Así S01..S12 mantienen identidad aunque cambien de caja/rack.
        cell = deepcopy(extra or {})
        cell["color"] = color
        cell.setdefault("id", f"UNKNOWN_{color}_{now_iso()}")
        cell["location"] = f"cell{slot}"
        cell["stored_at"] = now_iso()
        self.rack_cells[slot]["cell"] = cell
        print(f"[Rack][Memory] {cell.get('id')} ({color}) guardada en cell{slot}")
        return True
    def remove_cell_from_rack(self, slot: int) -> Optional[Dict[str, Any]]:
        cell = deepcopy(self.rack_cells[slot]["cell"])
        self.rack_cells[slot]["cell"] = None
        return cell
    def find_rack_cell_by_color(self, color: str) -> Optional[int]:
        if color not in VALID_COLORS:
            return None
        for slot in RACK_CELLS_BY_COLOR[color]:
            cell = self.rack_cells[slot]["cell"]
            if isinstance(cell, dict) and cell.get("color") == color:
                return slot
        return None
    def get_closed_box_with_lid_from_camera(self, results: Dict[str, Any]) -> Optional[Tuple[int, str]]:
        for slot_id in RACK_SLOT_IDS:
            box_slot = RACK_SLOT_TO_NUM[slot_id]
            slot = results.get(slot_id, {}) or {}
            box = self.boxes[box_slot]

            if not slot.get("box_present", False):
                continue
            if slot.get("confirmed_open", False):
                continue

            # No reprocesar cajas ya terminadas.
            # Antes una caja cerrada completa podía volver a detectarse como
            # caja nueva porque lid_collected=False tras cerrar.
            if box["state"] in ["closed_complete", "finished"]:
                continue

            # Si ya conocemos una caja en ese slot y no está en estado inicial,
            # no la tratamos como caja nueva aunque la cámara siga viendo tapa.
            if box["present"] and box["state"] not in ["empty", "closed"]:
                continue

            lid_color = slot.get("lid_color")
            if lid_color not in VALID_COLORS:
                print(
                    f"[CajaConTapa] {slot_id}: caja presente pero tapa no fiable "
                    f"state={slot.get('box_state')} lid={lid_color}"
                )
                continue

            if box["present"] and box["lid_collected"]:
                continue

            return box_slot, lid_color

        return None
    def register_box_with_lid(self, box_slot: int, lid_color: str) -> None:
        existing_box = self.boxes.get(box_slot, {}) or {}
        existing_lid_color = existing_box.get("detected_lid_color")
        if existing_box.get("present", False) and existing_lid_color in VALID_COLORS:
            if lid_color != existing_lid_color:
                print(
                    f"[LidMemory] Box{box_slot}: ignoro recolor de tapa "
                    f"{existing_lid_color} -> {lid_color}; identidad ya fijada."
                )
            lid_color = existing_lid_color

        self.boxes[box_slot] = {
            "present": True,

            # IMPORTANTE:
            # La caja todavía no tiene color fiable hasta quitar la tapa.
            "color": None,

            "state": "closed",
            "lid_collected": False,
            "cells_locked": False,
            "initial_cells_captured": False,
            "awaiting_direct_open_capture": False,
            "cells": [None, None, None, None],
            "bridge_parts_done": {piece_type: False for piece_type in BRIDGE_REQUIRED_TYPES},
            "bridge_parts_info": {},

            # La tapa sí tiene color y se guarda aparte.
            "detected_lid_color": lid_color,
            "lid_visual_name": (LID_OBJECTS.get(rack_slot_id(box_slot), {}) or {}).get(lid_color),
            "detected_box_color": None,

            "detected_at": now_iso(),
            "finished_at": None,
        }

        print(
            f"[Memory] Caja detectada en Box{box_slot} con tapa {lid_color}. "
            f"Color de caja pendiente hasta abrir."
        )
    def update_active_box_color_from_open_vision(self, results: Dict[str, Any]) -> bool:
        """
        Cuando ya se ha retirado la tapa, la cámara ve la caja abierta.
        En ese momento se guarda el color real de la caja.
        """
        if self.active_box_slot is None:
            return False

        box_slot = self.active_box_slot
        slot_state = results.get(rack_slot_id(box_slot), {}) or {}

        if not slot_state.get("box_present", False):
            return False

        if not slot_state.get("confirmed_open", False):
            return False

        open_box_color = slot_state.get("open_box_color", None)

        if open_box_color not in VALID_COLORS:
            print(
                f"[BoxColor] Box{box_slot}: esperando color real de caja abierta. "
                f"open_box_color={open_box_color}"
            )
            return False

        current_color = self.boxes[box_slot].get("color")

        if current_color == open_box_color:
            return True

        if current_color is not None and current_color != open_box_color:
            print(
                f"[BoxColor][AVISO] Box{box_slot}: cambio de color "
                f"{current_color} -> {open_box_color}"
            )

        self.boxes[box_slot]["color"] = open_box_color
        self.boxes[box_slot]["detected_box_color"] = open_box_color
        self.boxes[box_slot]["box_color_detected_at"] = now_iso()

        print(f"[BoxColor] Box{box_slot}: color real de caja = {open_box_color}")

        return True
    def mark_lid_collected(self, box_slot: int, lid_color: str, store_in_rack: bool = True) -> None:
        self.boxes[box_slot]["state"] = "open_waiting_cells"
        self.boxes[box_slot]["lid_collected"] = True
        self.boxes[box_slot]["cells_locked"] = False
        self.boxes[box_slot]["initial_cells_captured"] = False
        self.boxes[box_slot]["awaiting_direct_open_capture"] = False
        self.boxes[box_slot]["lid_collected_at"] = now_iso()
        if store_in_rack:
            self.store_lid(lid_color)
        self.active_box_slot = box_slot
        self.reset_open_box_confirmation()
        if store_in_rack:
            print(f"[Memory] Tapa {lid_color} de Box{box_slot} guardada en Lid{LID_SLOT_BY_COLOR[lid_color]}")
        else:
            print(f"[Memory] Tapa {lid_color} retirada de Box{box_slot} y no guardada en rack.")
    def start_pending_lid_transfer(
        self,
        box_slot: int,
        lid_color: str,
        target_box_slot: Optional[int] = None,
    ) -> None:
        self.mark_lid_collected(box_slot, lid_color, store_in_rack=False)
        self.pending_lid_transfer = {
            "source_box_slot": int(box_slot),
            "lid_color": str(lid_color),
            "target_box_slot": None if target_box_slot is None else int(target_box_slot),
            "transfer_mode": "direct_box" if target_box_slot is not None else "store",
            "visualized_open_box": False,
            "created_at": now_iso(),
        }
        if target_box_slot is not None:
            self.boxes[box_slot]["awaiting_direct_open_capture"] = True
        if target_box_slot is None:
            print(f"[LidFlow] Box{box_slot}: tapa en PrepareLid con destino ya decidido = rack.")
        else:
            print(
                f"[LidFlow] Box{box_slot}: tapa en PrepareLid con destino ya decidido = "
                f"Box{target_box_slot}."
            )
    def pick_lid(
        self,
        box_slot: int,
        lid_color: Optional[str] = None,
        *,
        direct_transfer: bool = False,
    ) -> bool:
        if box_slot not in [1, 2, 3]:
            print(f"[PickLid][ERROR] Posición inválida: {box_slot}")
            return False

        self.lock_visual_updates(f"pick_lid Box{box_slot}")
        try:
            steps = [
                lambda: self.set_box_frame(box_slot),
                self.gripperlidopen,
                # Keep the pre-pick hand-clear check even for a direct transfer.
                lambda: self.movej_target("PrepareLid"),
                lambda: self._wait_for_hand_clear("PrepareLid_wait"),
                lambda: self.movej_target("Lid"),
                lambda: self.movel_target("LidPick"),
                lambda: self.gripperlidclose(lid_color),
                lambda bs=box_slot, lc=lid_color: self._record_picked_lid_from_box(bs, lc),
                lambda: self.movel_target("Lid"),
            ]
            if not direct_transfer:
                steps.append(lambda: self.movej_target("PrepareLid"))
            steps.append(lambda: self.wait_move("PickLid"))

            return self.sequence(
                f"[PickLid] Retirando tapa de Box{box_slot}",
                *steps,
            )
        finally:
            self.unlock_visual_updates(f"pick_lid Box{box_slot} finalizado")

    def _wait_for_hand_clear(self, context: str = "wait_hand_clear", timeout_s: Optional[float] = None) -> bool:
        """Bloquea hasta que la cámara deje de ver la mano o hasta timeout.

        Devuelve False si se detecta una parada segura del robot o si expira el timeout.
        """
        import time

        start = time.time()
        cleared_since = None
        required_clear_s = 1.0

        while True:
            if getattr(self, "robot_safety_stop_active", False):
                print(f"[PickLid][AVISO] Abortando {context}: parada segura del robot.")
                return False

            last_hand = getattr(self, "last_hand_state", {}) or {}
            # Considerar presencia de mano en cualquier zona detectada.
            hand_present = bool(
                last_hand.get("hand_on_camera", False)
                or last_hand.get("hand_on_red", False)
                or last_hand.get("hand_on_green", False)
            )

            if not hand_present:
                if cleared_since is None:
                    cleared_since = time.time()
                else:
                    if (time.time() - cleared_since) >= required_clear_s:
                        return True
            else:
                cleared_since = None

            if timeout_s is not None and (time.time() - start) > float(timeout_s):
                print(f"[PickLid][AVISO] Timeout esperando a que la mano se retire ({timeout_s}s).")
                return False

            time.sleep(0.05)
    def place_lid(self, lid_color: str) -> bool:
        if lid_color not in VALID_COLORS:
            print(f"[PlaceLid][ERROR] Color inválido: {lid_color}")
            return False

        lid_slot = LID_SLOT_BY_COLOR[lid_color]
        return self.sequence(
            f"[PlaceLid] Guardando tapa {lid_color} en Lid{lid_slot}",
            lambda: self.movej_target("PrepareLid"),
            lambda: self.set_lid_frame(lid_slot),
            lambda: self.movej_target("lidout"),
            lambda: self.movej_target("lidup"),
            lambda: self.movel_target("liddown"),
            self.gripperlidout,
            # Al colocar en rack, eliminar la tapa de la lista de tapas en mano
            lambda lc=lid_color: self._remove_picked_lid_by_color(lc),
            lambda: self.movej_target("lidout"),
            lambda: self.movej_target("PlaceCell"),
            lambda: self.wait_move("PlaceLid"),
        )
    def find_completed_box_ready_for_lid_color(
        self,
        lid_color: str,
        exclude_box_slot: Optional[int] = None,
    ) -> Optional[int]:
        if lid_color not in VALID_COLORS:
            return None

        for box_slot in [1, 2, 3]:
            if exclude_box_slot is not None and box_slot == exclude_box_slot:
                continue

            box = self.boxes[box_slot]
            if (
                box["present"]
                and box["state"] == "bridge_ready"
                and box["color"] == lid_color
                and self.box_complete(box_slot)
            ):
                return box_slot

        return None
    def finalize_closed_box_with_direct_lid(self, box_slot: int) -> None:
        self.boxes[box_slot]["state"] = "closed_complete"
        self.boxes[box_slot]["lid_collected"] = False
        self.boxes[box_slot]["finished_at"] = now_iso()
        self.completed_boxes_count += 1
        print(f"[CloseBox] Box{box_slot} terminada con tapa directa.")
    def camera_results_slot_state(self, box_slot: int) -> Dict[str, Any]:
        return (self.last_camera_results.get(rack_slot_id(box_slot), {}) or {})
    def camera_open_box_complete(self, box_slot: int) -> bool:
        slot_state = self.camera_results_slot_state(box_slot)
        if not slot_state.get("box_present", False) or not slot_state.get("confirmed_open", False):
            return False

        box_color = slot_state.get("open_box_color", None)
        if box_color not in VALID_COLORS:
            return False

        batteries = slot_state.get("battery_slots", {}) or {}
        for cell_num in [1, 2, 3, 4]:
            cell_state = batteries.get(battery_slot_id(cell_num), {}) or {}
            if not cell_state.get("battery_present", False):
                return False
            if cell_state.get("battery_color") != box_color:
                return False
            if cell_state.get("polarity_ok") is not True:
                return False

        return True
    def memorize_box_cells_from_camera(self, box_slot: int) -> bool:
        slot_state = self.camera_results_slot_state(box_slot)
        box_color = slot_state.get("open_box_color", None)
        if box_color not in VALID_COLORS:
            return False

        self.boxes[box_slot]["color"] = box_color
        self.boxes[box_slot]["detected_box_color"] = box_color
        batteries = slot_state.get("battery_slots", {}) or {}
        for cell_num in [1, 2, 3, 4]:
            cell_state = batteries.get(battery_slot_id(cell_num), {}) or {}
            if not (
                cell_state.get("battery_present", False)
                and cell_state.get("battery_color") == box_color
                and cell_state.get("polarity_ok") is True
            ):
                return False
            cell_obj = self.known_or_detected_cell(box_slot, cell_num, box_color, True)
            self.mark_cell_in_box(box_slot, cell_num, cell_obj, ok=True, source="camera", polarity_ok=True)

        return True
    def preview_open_box_cells_from_camera(self, box_slot: int) -> bool:
        box = self.boxes.get(box_slot, {}) or {}
        if box.get("initial_cells_captured", False):
            return True

        slot_state = self.camera_results_slot_state(box_slot)
        if not slot_state.get("box_present", False) or not slot_state.get("confirmed_open", False):
            return False

        missing_cells = missing_visible_battery_slots(slot_state)
        if missing_cells:
            print(
                f"[LidFlow] Box{box_slot}: esperando las 4 celdas visibles antes de continuar; "
                f"faltan {', '.join(missing_cells)}."
            )
            return False

        box_color = slot_state.get("open_box_color", None)
        if box_color not in VALID_COLORS:
            print(
                f"[LidFlow] Box{box_slot}: esperando color fiable de caja abierta "
                f"antes de fijar celdas; open_box_color={box_color}."
            )
            return False

        batteries = slot_state.get("battery_slots", {}) or {}
        invalid_color_cells = [
            battery_slot_id(cell_num)
            for cell_num in [1, 2, 3, 4]
            if (batteries.get(battery_slot_id(cell_num), {}) or {}).get("battery_color")
            not in VALID_COLORS
        ]
        if invalid_color_cells:
            print(
                f"[LidFlow] Box{box_slot}: esperando colores fiables de las 4 celdas; "
                f"invalidas {', '.join(invalid_color_cells)}."
            )
            return False

        self.boxes[box_slot]["color"] = box_color
        self.boxes[box_slot]["detected_box_color"] = box_color
        for cell_num in [1, 2, 3, 4]:
            cell_state = batteries.get(battery_slot_id(cell_num), {}) or {}
            color = cell_state.get("battery_color")
            polarity_ok = cell_state.get("polarity_ok")

            cell_obj = self.known_or_detected_cell(box_slot, cell_num, color, polarity_ok)
            self.mark_cell_in_box(
                box_slot,
                cell_num,
                cell_obj,
                ok=(color == box_color and polarity_ok is True),
                source="camera_preview",
                polarity_ok=polarity_ok,
            )

        self.boxes[box_slot]["initial_cells_captured"] = True
        self.boxes[box_slot]["awaiting_direct_open_capture"] = False
        print(f"[LidFlow] Box{box_slot}: captura inicial de 4 celdas completada tras retirar la tapa.")
        return True
    def refresh_last_camera_results_from_memory(self) -> None:
        self.last_camera_results = self.freeze_results_for_live_update(self.last_camera_results)
        self.last_camera_summary = self.compact_camera_summary(self.last_camera_results)
    def find_closed_donor_box_for_lid_color(
        self,
        lid_color: str,
        exclude_box_slot: Optional[int] = None,
    ) -> Optional[int]:
        if lid_color not in VALID_COLORS:
            return None

        for box_slot in [1, 2, 3]:
            if exclude_box_slot is not None and box_slot == exclude_box_slot:
                continue

            box = self.boxes[box_slot]
            if not box.get("present", False):
                continue
            if box.get("state") not in ["closed_complete", "finished"]:
                continue
            if box.get("detected_lid_color") != lid_color:
                continue
            if not self.box_complete(box_slot):
                continue
            if not self.bridge_complete(box_slot):
                continue
            return box_slot

        return None
    def reopen_completed_box_after_lid_pick(self, box_slot: int, lid_color: str) -> None:
        box = self.boxes[box_slot]
        was_finished = box.get("state") in ["closed_complete", "finished"]

        box["state"] = "bridge_ready"
        box["lid_collected"] = True
        box["cells_locked"] = True
        box["detected_lid_color"] = None
        box["finished_at"] = None

        if was_finished and self.completed_boxes_count > 0:
            self.completed_boxes_count -= 1

        self.active_box_slot = None
        robodk_updater = getattr(self, "robodk_updater", None)
        if robodk_updater is not None and hasattr(robodk_updater, "reopen_completed_box_from_station"):
            robodk_updater.reopen_completed_box_from_station(box_slot)
        self.refresh_last_camera_results_from_memory()
        print(f"[LidFlow] Box{box_slot}: tapa {lid_color} retirada de caja cerrada. Caja reabierta y lista para esperar tapa.")
    def handle_picked_lid_at_prepare(
        self,
        source_box_slot: int,
        lid_color: str,
        target_box_slot: Optional[int] = None,
    ) -> Tuple[bool, str]:
        time.sleep(LID_POST_PICK_ANALYZE_S)
        self.preview_open_box_cells_from_camera(source_box_slot)
        return self.place_removed_lid(source_box_slot, lid_color, target_box_slot=target_box_slot)
    def place_removed_lid(
        self,
        source_box_slot: int,
        lid_color: str,
        target_box_slot: Optional[int] = None,
    ) -> Tuple[bool, str]:
        if target_box_slot is None:
            return self.place_lid(lid_color), "stored"

        print(
            f"[LidFlow] La tapa {lid_color} de Box{source_box_slot} "
            f"se usara directamente para cerrar Box{target_box_slot}."
        )

        # Leave the destination box through the safe lid waypoint before any
        # later bridge sequence can start.
        ok = self.place_lid_on_box(target_box_slot, return_to_prepare_lid=True)
        if ok:
            self.finalize_closed_box_with_direct_lid(target_box_slot)
            # The robot is already lifted above the destination box. Only now
            # preview the newly opened source box; its normal processing will
            # keep waiting if not all four cells are visible yet.
            if not self.preview_open_box_cells_from_camera(source_box_slot):
                self.active_box_slot = source_box_slot
                self.boxes[source_box_slot]["awaiting_direct_open_capture"] = True
                print(
                    f"[LidFlow] Box{source_box_slot}: tapa transferida directamente; "
                    "esperando frame abierto fiable para fijar color y celdas."
                )
            self.refresh_last_camera_results_from_memory()
            return True, "reused_other_box"
        return False, "failed"

    # ----------------- Helpers for tracking picked lids -----------------
    def _record_picked_lid_from_box(self, box_slot: int, lid_color: Optional[str]) -> bool:
        try:
            box = self.boxes.get(box_slot, {}) or {}
            visual_name = box.get("lid_visual_name")
            if lid_color in VALID_COLORS:
                visual_name = visual_name or (LID_OBJECTS.get(rack_slot_id(box_slot), {}) or {}).get(lid_color)
            lid = {
                "id": f"LID_box{box_slot}_{lid_color}_{now_iso()}",
                "color": lid_color,
                "source": f"box{box_slot}",
                "visual_name": visual_name,
                "picked_at": now_iso(),
            }
            if len(self.picked_lids) >= 3:
                print(f"[LidMemory][AVISO] Intentando coger >3 tapas; ignorando registro: {lid}")
                return False
            self.picked_lids.append(lid)
            robodk_updater = getattr(self, "robodk_updater", None)
            if robodk_updater is not None and hasattr(robodk_updater, "release_lid_from_slot"):
                robodk_updater.release_lid_from_slot(box_slot, visual_name=visual_name)
            box["lid_visual_name"] = None
            print(f"[LidMemory] Tapa pickeada y registrada: {lid}")
            return True
        except Exception as exc:
            print(f"[LidMemory][AVISO] No se pudo registrar tapa pickeada: {exc}")
            return False

    def _record_picked_lid_from_storage(self, lid_color: str) -> bool:
        try:
            slot = LID_SLOT_BY_COLOR[lid_color]
            stored = self.lid_slots[slot].get("stored")
            lid = deepcopy(stored) if isinstance(stored, dict) else {"id": f"LID_storage_{lid_color}_{now_iso()}", "color": lid_color, "source": f"Lid{slot}", "picked_at": now_iso()}
            if len(self.picked_lids) >= 3:
                print(f"[LidMemory][AVISO] Intentando recuperar >3 tapas; ignorando registro: {lid}")
                return False
            self.picked_lids.append(lid)
            # Quitar de storage inmediatamente al recoger
            self.lid_slots[slot]["stored"] = None
            print(f"[LidMemory] Tapa recogida desde storage y registrada: {lid}")
            return True
        except Exception as exc:
            print(f"[LidMemory][AVISO] No se pudo registrar tapa desde storage: {exc}")
            return False

    def _remove_picked_lid_by_color(self, color: str) -> bool:
        try:
            for idx, lid in enumerate(self.picked_lids):
                if lid.get("color") == color:
                    removed = self.picked_lids.pop(idx)
                    self.last_stored_lid = deepcopy(removed)
                    print(f"[LidMemory] Tapa colocada/descartada: {removed}")
                    return True
            print(f"[LidMemory][AVISO] No se encontro tapa en mano con color {color} para eliminar")
            return False
        except Exception as exc:
            print(f"[LidMemory][AVISO] Error al eliminar tapa en mano: {exc}")
            return False

    def _pop_picked_lid_for_box(self, box_slot: int) -> Optional[Dict[str, Any]]:
        # Cuando se coloca una tapa en una caja, preferimos seleccionar la tapa
        # en mano que coincide con el color esperado de la caja.
        try:
            box = self.boxes.get(box_slot, {}) or {}
            color = box.get("color") or box.get("detected_lid_color")
            if color in VALID_COLORS:
                for idx, lid in enumerate(self.picked_lids):
                    if lid.get("color") == color:
                        return self.picked_lids.pop(idx)

            # Fallback: pop la primera si existe
            if self.picked_lids:
                return self.picked_lids.pop(0)
            return None
        except Exception as exc:
            print(f"[LidMemory][AVISO] Error al obtener tapa en mano para Box{box_slot}: {exc}")
            return None

    def _simulate_lid_drop_from_memory(self, box_slot: int) -> bool:
        """Pop una tapa en mano (si existe) y solicitar al updater que mueva
        la visual correcta sobre la caja destino.
        """
        try:
            picked = self._pop_picked_lid_for_box(box_slot)
            lid_color = None
            visual_name = None
            if isinstance(picked, dict):
                lid_color = picked.get("color")
                visual_name = picked.get("visual_name")

            # Fallback: usar la informacion de la caja si no hay tapa en mano
            box = self.boxes.get(box_slot, {}) or {}
            if lid_color is None:
                lid_color = box.get("color") or box.get("detected_lid_color")
            if visual_name is not None:
                box["lid_visual_name"] = visual_name

            robodk_updater = getattr(self, "robodk_updater", None)
            if robodk_updater is None:
                return True

            ok = robodk_updater.simulate_lid_gravity_drop_on_box(box_slot, lid_color, visual_name=visual_name)
            if not ok:
                print(f"[LidFlow][AVISO] Simulacion visual de tapa fallida para Box{box_slot} color={lid_color} visual={visual_name}")
            return True
        except Exception as exc:
            print(f"[LidFlow][AVISO] Error al simular bajada visual de tapa para Box{box_slot}: {exc}")
            return False
    def close_completed_box_with_direct_donor_lid(self, target_box_slot: int, donor_box_slot: int) -> bool:
        color = self.boxes[target_box_slot]["color"]
        if color not in VALID_COLORS:
            print(f"[CloseBox][ERROR] Box{target_box_slot} sin color fiable para tapa directa: {color}")
            return False

        print(
            f"[LidFlow] Box{target_box_slot}: sin tapa en rack. "
            f"Usando tapa {color} directamente desde Box{donor_box_slot}."
        )

        if not self.pick_lid(donor_box_slot, color, direct_transfer=True):
            return False

        self.reopen_completed_box_after_lid_pick(donor_box_slot, color)

        # Direct transfer: place first and inspect the opened donor only once
        # the robot has released the lid and lifted from the destination.
        # Do not allow the next bridge cycle to start from above the lid box.
        ok2 = self.place_lid_on_box(target_box_slot, return_to_prepare_lid=True)
        if not ok2:
            return False

        self.finalize_closed_box_with_direct_lid(target_box_slot)
        self.preview_open_box_cells_from_camera(donor_box_slot)
        # Refrescar la pose visual por si hace falta (asegura posición correcta)
        self.refresh_last_camera_results_from_memory()
        return True
    def resolve_pending_lid_transfer(self) -> bool:
        pending = self.pending_lid_transfer or {}
        if not pending:
            return False

        source_box_slot = int(pending.get("source_box_slot"))
        lid_color = str(pending.get("lid_color"))
        target_box_slot = pending.get("target_box_slot")
        if target_box_slot is not None:
            target_box_slot = int(target_box_slot)

        if target_box_slot is not None:
            ok, outcome = self.place_removed_lid(
                source_box_slot,
                lid_color,
                target_box_slot=target_box_slot,
            )
            if ok:
                self.pending_lid_transfer = None
            else:
                print(f"[StationLogic][AVISO] Pendiente tapa Box{source_box_slot}: no se completo el movimiento.")
            return bool(ok)

        if not bool(pending.get("visualized_open_box", False)):
            if not self.preview_open_box_cells_from_camera(source_box_slot):
                slot_state = self.camera_results_slot_state(source_box_slot)
                batteries = slot_state.get("battery_slots", {}) or {}
                visible_cells = [
                    battery_id
                    for battery_id, cell_state in batteries.items()
                    if (cell_state or {}).get("battery_present", False)
                ]
                print(
                    f"[LidFlow] Box{source_box_slot}: esperando vision abierta antes de mover la tapa. "
                    f"camera=(box_present={slot_state.get('box_present')}, "
                    f"box_state={slot_state.get('box_state')}, "
                    f"confirmed_open={slot_state.get('confirmed_open')}, "
                    f"lid_color={slot_state.get('lid_color')}, "
                    f"open_box_color={slot_state.get('open_box_color')}, "
                    f"visible_cells={visible_cells})"
                )
                return False
            pending["visualized_open_box"] = True
            self.pending_lid_transfer = pending
            print(f"[LidFlow] Box{source_box_slot}: celdas visualizadas en RoboDK. Tapa se movera en el siguiente ciclo.")
            return False

        ok, outcome = self.handle_picked_lid_at_prepare(
            source_box_slot,
            lid_color,
            target_box_slot=target_box_slot,
        )
        if ok and outcome == "stored":
            self.store_lid(lid_color, extra=getattr(self, "last_stored_lid", None))
            self.last_stored_lid = None
            print(f"[Memory] Tapa {lid_color} de Box{source_box_slot} guardada en Lid{LID_SLOT_BY_COLOR[lid_color]}")

        if ok:
            self.pending_lid_transfer = None
        elif not ok:
            print(f"[StationLogic][AVISO] Pendiente tapa Box{source_box_slot}: no se completo el movimiento.")

        return bool(ok)
    def process_first_closed_box_with_lid(self, results: Dict[str, Any]) -> bool:
        detected = self.get_closed_box_with_lid_from_camera(results)
        if detected is None:
            return False

        box_slot, lid_color = detected
        target_box_slot = self.find_completed_box_ready_for_lid_color(
            lid_color,
            exclude_box_slot=box_slot,
        )
        self.register_box_with_lid(box_slot, lid_color)

        print(f"[Box{box_slot}] Secuencia tapa {lid_color}")
        if target_box_slot is None:
            print(f"[LidFlow] Box{box_slot}: antes del pick, destino de tapa = rack.")
        else:
            print(f"[LidFlow] Box{box_slot}: antes del pick, destino de tapa = Box{target_box_slot}.")
        ok = self.pick_lid(
            box_slot,
            lid_color,
            direct_transfer=target_box_slot is not None,
        )
        if ok:
            self.start_pending_lid_transfer(box_slot, lid_color, target_box_slot=target_box_slot)
            return True
        else:
            print(f"[StationLogic][AVISO] No se completó la retirada/guardado de tapa Box{box_slot}")

        return False
