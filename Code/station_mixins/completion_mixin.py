"""StationLogic CompletionMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *


class CompletionMixin:
    def find_completed_box_ready_to_close(self) -> Optional[int]:
        for box_slot in [1, 2, 3]:
            box = self.boxes[box_slot]
            color = box["color"]
            if (
                box["present"]
                and box["state"] == "bridge_ready"
                and color in VALID_COLORS
                and self.box_complete(box_slot)
            ):
                return box_slot
        return None
    def retrieve_lid_from_storage(self, lid_color: str) -> bool:
        if not self.lid_available(lid_color):
            print(f"[RetrieveLid] No hay tapa {lid_color} disponible")
            return False

        lid_slot = LID_SLOT_BY_COLOR[lid_color]
        return self.sequence(
            f"[RetrieveLid] Cogiendo tapa {lid_color} desde Lid{lid_slot}",
            lambda: self.movej_target("PrepareLid"),
            lambda: self.set_lid_frame(lid_slot),
            lambda: self.movej_target("lidpos"),
            lambda: self.movel_target("lidgo"),
            lambda: self.gripperlidclose(lid_color),
            # Registrar que hemos pickeado la tapa desde storage
            lambda lc=lid_color: self._record_picked_lid_from_storage(lc),
            lambda: self.movel_target("lidup"),
            lambda: self.movej_target("lidout"),
            lambda: self.movej_target("PrepareLid"),
        )
    def place_lid_on_box(self, box_slot: int, *, return_to_prepare_lid: bool = True) -> bool:
        steps = [
            lambda: self.set_box_frame(box_slot),
            lambda: self.movej_target("Lid"),
            lambda: self.movel_target("Lidd"),
            self.gripperlidopen,
            # Usar la tapa almacenada en memoria (si hay) y simular su caída visual
            lambda bs=box_slot: self._simulate_lid_drop_from_memory(bs),
            lambda: self.movel_target("Lid"),
        ]
        if return_to_prepare_lid:
            steps.append(lambda: self.movej_target("PrepareLid"))

        return self.sequence(
            f"[PlaceLidOnBox] Colocando tapa en Box{box_slot}",
            *steps,
        )
    def simulate_lid_gravity_drop_on_box(self, box_slot: int) -> bool:
        box = self.boxes.get(box_slot, {}) or {}
        lid_color = box.get("color") or box.get("detected_lid_color")
        visual_name = box.get("lid_visual_name")

        robodk_updater = getattr(self, "robodk_updater", None)
        if robodk_updater is None or not hasattr(robodk_updater, "simulate_lid_gravity_drop_on_box"):
            return True

        ok = robodk_updater.simulate_lid_gravity_drop_on_box(box_slot, lid_color, visual_name=visual_name)
        if not ok:
            print(
                f"[PlaceLidOnBox][AVISO] No se pudo simular gravedad visual "
                f"para tapa {lid_color} en Box{box_slot}; continuo ciclo robot."
            )
        return True
    def close_completed_box(self, box_slot: int) -> bool:
        color = self.boxes[box_slot]["color"]
        if color not in VALID_COLORS:
            print(f"[CloseBox][ERROR] Box{box_slot} sin color fiable: {color}")
            return False

        if not self.lid_available(color):
            donor_box_slot = self.find_closed_donor_box_for_lid_color(color, exclude_box_slot=box_slot)
            if donor_box_slot is not None:
                return self.close_completed_box_with_direct_donor_lid(box_slot, donor_box_slot)
            print(f"[CloseBox] Box{box_slot}: tapa {color} no disponible ni en rack ni en otra caja cerrada.")
            return False

        ok = self.sequence(
            f"[CloseBox] Cerrando Box{box_slot} con tapa {color}",
            lambda: self.retrieve_lid_from_storage(color),
            lambda: self.place_lid_on_box(box_slot),
        )

        if ok:
            self.remove_lid(color)
            self.boxes[box_slot]["state"] = "closed_complete"
            self.boxes[box_slot]["lid_collected"] = False
            self.boxes[box_slot]["cells_locked"] = True
            self.boxes[box_slot]["finished_at"] = now_iso()
            self.active_box_slot = None
            self.completed_boxes_count += 1
            print(f"[CloseBox] Box{box_slot} terminada.")

        return ok
    def try_close_completed_boxes(self) -> bool:
        did_action = False
        while True:
            box_slot = self.find_completed_box_ready_to_close()
            if box_slot is None:
                break
            if not self.close_completed_box(box_slot):
                break
            did_action = True
        return did_action
    def all_station_boxes_finished(self) -> bool:
        return all(
            box["state"] in ["closed_complete", "finished"]
            for box in self.boxes.values()
        )
    def move_to_prepare_lid_wait(self) -> bool:
        return self.sequence(
            "[StationLogic] Moviendo robot a PrepareLid para esperar la siguiente tapa/caja.",
            lambda: self.movej_target("PrepareLid"),
        )
    def move_to_pick_cell_wait(self) -> bool:
        return self.sequence(
            "[StationLogic] Volviendo a PlaceCell para esperar la siguiente caja.",
            lambda: self.movej_target("PlaceCell"),
        )
    def try_fill_pending_boxes_from_rack(self, results: Dict[str, Any]) -> bool:
        did_action = False
        for box_slot in [1, 2, 3]:
            box = self.boxes[box_slot]
            if not box["present"] or not box["lid_collected"] or self.box_complete(box_slot):
                continue

            slot_state = results.get(rack_slot_id(box_slot), {}) or {}
            if not (slot_state.get("box_present", False) and slot_state.get("confirmed_open", False)):
                continue

            required_color = box["color"]
            if required_color not in VALID_COLORS:
                continue

            for cell_num in [1, 2, 3, 4]:
                cell = box["cells"][cell_num - 1]
                if isinstance(cell, dict) and cell.get("ok") is True:
                    continue
                if self.find_rack_cell_by_color(required_color) is None:
                    break
                did_action |= self.try_fill_cell_from_rack(box_slot, cell_num, required_color)

            if self.box_complete(box_slot):
                self.buscar_bridge(box_slot, results)
                did_action = True

        return did_action
    def sync_finished_boxes_removed_from_camera(self, results: Dict[str, Any]) -> None:
        for slot_id in RACK_SLOT_IDS:
            box_slot = RACK_SLOT_TO_NUM[slot_id]
            slot = results.get(slot_id, {}) or {}
            box = self.boxes[box_slot]

            if slot.get("box_present", False):
                continue

            if box["state"] in ["closed_complete", "finished"]:
                print(f"[Memory] Box{box_slot} terminada retirada de cámara -> slot libre")
                self.boxes[box_slot] = empty_box_state()
    def station_has_unfinished_known_boxes(self) -> bool:
        return any(
            box["present"] and box["state"] not in ["closed_complete", "finished", "empty", None]
            for box in self.boxes.values()
        )
    def maybe_pause_when_all_done(self, results: Dict[str, Any]) -> bool:
        if self.completed_boxes_count <= 0:
            return False
        if self.active_box_slot is not None:
            return False
        if self.station_has_unfinished_known_boxes():
            return False
        if self.get_closed_box_with_lid_from_camera(results) is not None:
            return False

        self.move_to_prepare_lid_wait()
        self.paused = True
        print("[StationLogic] Todas las cajas conocidas están cerradas. Programa pausado.")
        return True
    def freeze_results_for_live_update(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Ajusta los results para que RoboDK muestre la memoria lógica actual.

        La cámara puede seguir enviando durante unos frames una caja cerrada, una
        tapa o una celda que la lógica ya ha movido. Este método evita que el
        gemelo de RoboDK vuelva a mostrar esos objetos desde el último frame
        crudo de visión.

        NUEVO:
        - Si la caja está recién abierta (state == "open_waiting_cells") y todavía
        no hay ninguna celda en memoria (cells todas a None), se dejan los
        battery_slots tal cual vienen de cámara para ver las celdas en tiempo real.
        - Cuando ya hay celdas en memoria, se vuelve al comportamiento original:
        usar memoria (cells) para construir battery_slots y congelar la vista.
        """
        live = deepcopy(results or {})

        for box_slot in [1, 2, 3]:
            slot_id = rack_slot_id(box_slot)
            slot_live = deepcopy(live.get(slot_id, {}) or {})
            box = self.boxes.get(box_slot, empty_box_state())

            if not box.get("present", False):
                live[slot_id] = slot_live
                continue

            box_color = box.get("color")
            lid_color = box.get("detected_lid_color")

            state = box.get("state", "unknown")

            # Si está cerrada y todavía no sabemos color de caja,
            # para RoboDK usamos visualmente el color de la tapa.
            if state in ["closed", "closed_complete", "finished"]:
                visual_color = box_color if box_color in VALID_COLORS else lid_color

                if visual_color not in VALID_COLORS:
                    live[slot_id] = slot_live
                    continue

                slot_live.update({
                    "box_present": True,
                    "box_state": "closed",
                    "confirmed_open": False,
                    "lid_color": visual_color,
                    "open_box_color": None,
                    "battery_slots": {},
                })
                live[slot_id] = slot_live
                continue

            # Si está abierta/en proceso, ahora sí hace falta color real de caja.
            if box_color not in VALID_COLORS:
                live[slot_id] = slot_live
                continue

            color = box_color
            state = box.get("state", "unknown")

            # Caja cerrada o ya finalizada: mostrar caja + tapa, sin baterías.
            if state in ["closed", "closed_complete", "finished"]:
                slot_live.update({
                    "box_present": True,
                    "box_state": "closed",
                    "confirmed_open": False,
                    "lid_color": color,
                    "open_box_color": None,
                    "battery_slots": {},
                })
                live[slot_id] = slot_live
                continue

            # Caja con tapa retirada/en proceso: mostrar caja abierta.
            if box.get("lid_collected", False) or state in [
                "open_waiting_cells",
                "processing_cells",
                "waiting_rack_cells",
                "cells_complete",
                "cells_complete_waiting_lid",
                "bridges_pending",
                "bridge_ready",
            ]:
                camera_batteries = (results.get(slot_id, {}) or {}).get("battery_slots", {}) or {}
                memory_batteries: Dict[str, Dict[str, Any]] = {}
                cells = box.get("cells", [None, None, None, None])

                # --- NUEVO BLOQUE ---
                # Caja recién abierta: todavía no hemos procesado ninguna celda.
                # Dejamos que RoboDK vea directamente lo que ve la cámara.
                if not bool(box.get("cells_locked", False)):
                    slot_live.update({
                        "box_present": True,
                        "box_state": "open",
                        "confirmed_open": True,
                        "lid_color": None,
                        "open_box_color": color,
                        "battery_slots": camera_batteries,
                    })
                    live[slot_id] = slot_live
                    continue
                # --- FIN NUEVO BLOQUE ---

                for cell_num in [1, 2, 3, 4]:
                    b_id = battery_slot_id(cell_num)
                    camera_cell = deepcopy(camera_batteries.get(b_id, {}) or {})
                    mem_cell = cells[cell_num - 1] if len(cells) >= cell_num else None

                    if isinstance(mem_cell, dict) and mem_cell.get("color") in VALID_COLORS:
                        memory_batteries[b_id] = {
                            "battery_present": True,
                            "battery_color": mem_cell.get("color"),
                            "polarity_ok": True if mem_cell.get("ok") is True else camera_cell.get("polarity_ok", None),
                            "cell_id": mem_cell.get("id"),
                        }
                    elif mem_cell is None:
                        memory_batteries[b_id] = {
                            "battery_present": False,
                            "battery_color": None,
                            "polarity_ok": None,
                        }
                    elif camera_cell:
                        memory_batteries[b_id] = camera_cell
                    else:
                        memory_batteries[b_id] = {
                            "battery_present": False,
                            "battery_color": None,
                            "polarity_ok": None,
                        }

                slot_live.update({
                    "box_present": True,
                    "box_state": "open",
                    "confirmed_open": True,
                    "lid_color": None,
                    "open_box_color": color,
                    "battery_slots": memory_batteries,
                })
                live[slot_id] = slot_live
                continue

            # Caso por defecto: no tocamos nada más.
            live[slot_id] = slot_live

        return live
