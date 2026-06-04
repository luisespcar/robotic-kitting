"""StationLogic CellProcessingMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *


class CellProcessingMixin:
    def try_fill_cell_from_rack(self, box_slot: int, cell_num: int, required_color: str) -> bool:
        rack_slot = self.find_rack_cell_by_color(required_color)
        if rack_slot is None:
            print(f"  Box{box_slot} C{cell_num}: no hay celda {required_color} en rack")
            self.set_box_cell(box_slot, cell_num, None)
            return False

        print(f"  Rack cell{rack_slot} -> Box{box_slot} C{cell_num}")

        picked = self.pick_cell_rack(rack_cell_slot=rack_slot, color=required_color)
        if picked is None:
            return False

        ok = self.place_cell_from_rack(cell_num, box_slot)
        if ok:
            self.mark_cell_in_box(
                box_slot,
                cell_num,
                picked,
                ok=True,
                source="rack",
                polarity_ok=True,
                extra={"rack_slot": rack_slot},
            )
            print(f"[Box][Memory] {picked.get('id')} colocada en Box{box_slot} C{cell_num}")
        else:
            print(
                f"[Rack][AVISO] Celda {picked.get('id', required_color)} sacada de cell{rack_slot}, "
                "pero no colocada. Revisar manualmente antes de continuar."
            )
        return ok
    def box_is_operational_for_cells(self, box_slot: int, results: Dict[str, Any]) -> bool:
        box = self.boxes[box_slot]
        slot_state = results.get(rack_slot_id(box_slot), {}) or {}

        return (
            box.get("present", False)
            and box.get("lid_collected", False)
            and box.get("color") in VALID_COLORS
            and not self.box_complete(box_slot)
            and slot_state.get("box_present", False)
            and slot_state.get("confirmed_open", False)
        )
    def camera_cell_state(self, results: Dict[str, Any], box_slot: int, cell_num: int) -> Dict[str, Any]:
        slot_state = results.get(rack_slot_id(box_slot), {}) or {}
        batteries = slot_state.get("battery_slots", {}) or {}
        return batteries.get(battery_slot_id(cell_num), {}) or {}
    def cell_needs_fill(
        self,
        box_slot: int,
        cell_num: int,
        results: Dict[str, Any],
        known_empty_cells: Optional[set] = None,
    ) -> bool:
        if known_empty_cells and (box_slot, cell_num) in known_empty_cells:
            return True

        stored_cell = self.boxes[box_slot]["cells"][cell_num - 1]
        if isinstance(stored_cell, dict) and stored_cell.get("ok") is True:
            return False

        camera_cell = self.camera_cell_state(results, box_slot, cell_num)
        return not camera_cell.get("battery_present", False)
    def find_direct_box_destination(
        self,
        source_box_slot: int,
        cell_color: str,
        results: Dict[str, Any],
        known_empty_cells: Optional[set] = None,
    ) -> Optional[Tuple[int, int]]:
        if cell_color not in VALID_COLORS:
            return None

        for dest_box_slot in [1, 2, 3]:
            if dest_box_slot == source_box_slot:
                continue
            if not self.box_is_operational_for_cells(dest_box_slot, results):
                continue
            if self.boxes[dest_box_slot]["color"] != cell_color:
                continue

            for dest_cell_num in [1, 2, 3, 4]:
                if self.cell_needs_fill(dest_box_slot, dest_cell_num, results, known_empty_cells):
                    return dest_box_slot, dest_cell_num

        return None
    def place_transferred_cell_in_box(
        self,
        source_box_slot: int,
        source_cell_num: int,
        dest_box_slot: int,
        dest_cell_num: int,
    ) -> bool:
        place_inverse = self.box_place_inverse_from_rack(dest_cell_num)
        return self.place_cell(
            dest_cell_num,
            dest_box_slot,
            inverse=place_inverse,
            source=f"Box{source_box_slot}C{source_cell_num}",
        )
    def transfer_wrong_color_cell(
        self,
        source_box_slot: int,
        source_cell_num: int,
        cell_obj: Dict[str, Any],
        color: str,
        polarity_ok: Optional[bool],
        results: Dict[str, Any],
        known_empty_cells: set,
        via_place_cell: bool = True,
    ) -> Tuple[bool, bool]:
        """Move a wrong-color cell and report whether motion can continue box-to-box.

        Returns ``(success, direct_box_transfer)``. A rack destination requires
        the next box pick to re-enter through PlaceCell; a direct box
        destination does not.
        """
        inverse_pick = self.box_pick_inverse_to_store_in_rack(source_cell_num, polarity_ok)
        destination = self.find_direct_box_destination(
            source_box_slot,
            color,
            results,
            known_empty_cells=known_empty_cells,
        )

        if destination is None:
            print(
                f"  Box{source_box_slot} C{source_cell_num}: {cell_obj.get('id')} "
                f"pick_inverse={inverse_pick} -> rack"
            )
        else:
            dest_box_slot, dest_cell_num = destination
            print(
                f"  Box{source_box_slot} C{source_cell_num}: {cell_obj.get('id')} "
                f"pick_inverse={inverse_pick} -> Box{dest_box_slot} C{dest_cell_num}"
            )

        if not self.pick_cell(
            source_cell_num,
            source_box_slot,
            inverse=inverse_pick,
            via_place_cell=via_place_cell,
        ):
            return False, False

        cell_obj.update({
            "source": f"Box{source_box_slot}C{source_cell_num}",
            "polarity_ok_when_picked": polarity_ok,
            "pick_inverse_used": inverse_pick,
            "rack_orientation": "red_right_standard",
        })

        if destination is None:
            stored_slot = self.place_cell_rack(color, extra=cell_obj)
            if stored_slot is None:
                return False, False

            self.set_box_cell(source_box_slot, source_cell_num, None)
            known_empty_cells.add((source_box_slot, source_cell_num))
            return True, False

        dest_box_slot, dest_cell_num = destination
        if not self.place_transferred_cell_in_box(source_box_slot, source_cell_num, dest_box_slot, dest_cell_num):
            print(
                f"[BoxTransfer][AVISO] {cell_obj.get('id', color)} cogida de "
                f"Box{source_box_slot} C{source_cell_num}, pero no colocada en Box{dest_box_slot} C{dest_cell_num}."
            )
            return False, False

        self.set_box_cell(source_box_slot, source_cell_num, None)
        known_empty_cells.add((source_box_slot, source_cell_num))
        self.mark_cell_in_box(
            dest_box_slot,
            dest_cell_num,
            cell_obj,
            ok=True,
            source=f"Box{source_box_slot}C{source_cell_num}",
            polarity_ok=True,
            extra={
                "transferred_from_box": source_box_slot,
                "transferred_from_cell": source_cell_num,
            },
        )
        return True, True
    def fill_operational_boxes_from_rack(
        self,
        results: Dict[str, Any],
        *,
        preferred_box_slot: Optional[int] = None,
        known_empty_cells: Optional[set] = None,
    ) -> bool:
        did_action = False
        ordered_slots = [slot for slot in [1, 2, 3] if slot == preferred_box_slot]
        ordered_slots += [slot for slot in [1, 2, 3] if slot != preferred_box_slot]

        for box_slot in ordered_slots:
            if not self.box_is_operational_for_cells(box_slot, results):
                continue

            required_color = self.boxes[box_slot]["color"]
            for cell_num in [1, 2, 3, 4]:
                if not self.cell_needs_fill(box_slot, cell_num, results, known_empty_cells):
                    continue

                if self.find_rack_cell_by_color(required_color) is None:
                    break

                did_action |= self.try_fill_cell_from_rack(box_slot, cell_num, required_color)

            if self.box_complete(box_slot):
                self.boxes[box_slot]["state"] = "cells_complete"

        return did_action
    def process_active_box_cells(self, results: Dict[str, Any]) -> bool:
        active = self.camera_active_open_box(results)
        if active is None:
            self.reset_open_box_confirmation()
            return False

        box_slot, slot_state = active
        if not self.active_open_box_vision_confirmed(box_slot, slot_state):
            return False

        # Primero actualizamos el color real de la caja desde visión abierta.
        if not self.boxes[box_slot].get("initial_cells_captured", False):
            if not self.preview_open_box_cells_from_camera(box_slot):
                return False

        self.update_active_box_color_from_open_vision(results)

        required_color = self.boxes[box_slot]["color"]

        if required_color not in VALID_COLORS:
            print(
                f"[Cells][AVISO] Box{box_slot}: color de caja todavía no fiable. "
                f"Esperando open_box_color desde visión."
            )
            return False

        print(f"[Cells] Procesando Box{box_slot} color={required_color}")
        self.boxes[box_slot]["state"] = "processing_cells"
        self.boxes[box_slot]["cells_locked"] = True
        did_action = False
        known_empty_cells = set()
        continue_without_place_cell = False

        batteries = slot_state.get("battery_slots", {}) or {}

        for cell_num in [1, 2, 3, 4]:
            if self.stop_cycle_if_needed(f"Box{box_slot} C{cell_num}"):
                return did_action

            b_id = battery_slot_id(cell_num)
            cell_state = batteries.get(b_id, {}) or {}
            stored_cell = self.boxes[box_slot]["cells"][cell_num - 1]
            if (
                self.boxes[box_slot].get("initial_cells_captured", False)
                and isinstance(stored_cell, dict)
                and stored_cell.get("color") in VALID_COLORS
                and cell_state.get("battery_present", False)
            ):
                cell_state = dict(cell_state)
                cell_state["battery_color"] = stored_cell["color"]

            if (
                isinstance(stored_cell, dict)
                and stored_cell.get("ok") is True
                and cell_state.get("battery_present", False)
                and cell_state.get("battery_color") == required_color
                and cell_state.get("polarity_ok") is True
            ):
                print(f"  Box{box_slot} C{cell_num}: OK ya memorizada")
                continue

            if not cell_state.get("battery_present", False):
                print(f"  Box{box_slot} C{cell_num}: vacío")
                self.set_box_cell(box_slot, cell_num, None)
                known_empty_cells.add((box_slot, cell_num))
                continue

            color = cell_state.get("battery_color")
            polarity_ok = cell_state.get("polarity_ok")

            if color == required_color and polarity_ok is True:
                print(f"  Box{box_slot} C{cell_num}: OK")
                cell_obj = self.known_or_detected_cell(box_slot, cell_num, color, polarity_ok)
                self.mark_cell_in_box(box_slot, cell_num, cell_obj, ok=True, source="camera", polarity_ok=True)
                continue

            if color == required_color and polarity_ok is False:
                print(f"  Box{box_slot} C{cell_num}: polaridad incorrecta -> rotar")
                cell_obj = self.known_or_detected_cell(box_slot, cell_num, color, polarity_ok)
                ok = self.rot_cell(
                    cell_num,
                    box_slot,
                    via_place_cell=not continue_without_place_cell,
                )
                if ok:
                    self.mark_cell_in_box(box_slot, cell_num, cell_obj, ok=True, source="rotated", polarity_ok=True)
                    did_action = True
                    continue_without_place_cell = True
                continue

            if color == required_color and polarity_ok is None:
                print(f"  Box{box_slot} C{cell_num}: polaridad desconocida -> esperar")
                cell_obj = self.known_or_detected_cell(box_slot, cell_num, color, polarity_ok)
                self.mark_cell_in_box(
                    box_slot,
                    cell_num,
                    cell_obj,
                    ok=False,
                    source="camera",
                    polarity_ok=None,
                    extra={"reason": "unknown_polarity"},
                )
                continue

            if color in VALID_COLORS:
                print(f"  Box{box_slot} C{cell_num}: color={color} incorrecto")
                cell_obj = self.known_or_detected_cell(box_slot, cell_num, color, polarity_ok)
                transfer_ok, direct_box_transfer = self.transfer_wrong_color_cell(
                    box_slot,
                    cell_num,
                    cell_obj,
                    color,
                    polarity_ok,
                    results,
                    known_empty_cells,
                    via_place_cell=not continue_without_place_cell,
                )
                did_action |= transfer_ok
                continue_without_place_cell = transfer_ok and direct_box_transfer
                continue

            print(f"  Box{box_slot} C{cell_num}: color no valido ({color}); no se mueve")

        did_action |= self.fill_operational_boxes_from_rack(
            results,
            preferred_box_slot=box_slot,
            known_empty_cells=known_empty_cells,
        )

        if self.box_complete(box_slot):
            self.boxes[box_slot]["cells_completed_at"] = now_iso()
            self.buscar_bridge(box_slot, results)
            print(f"[Cells] Box{box_slot}: celdas completas; entrando en secuencia bridge.")
        elif not did_action:
            self.boxes[box_slot]["state"] = "waiting_rack_cells"
            print(f"[Cells] Box{box_slot}: esperando rack/otra caja.")

        return did_action
