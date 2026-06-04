"""StationLogic CellMotionMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *


class CellMotionMixin:
    def cell_targets(self, cell_num: int, inverse: bool = False) -> Tuple[str, str]:
        if cell_num not in [1, 2, 3, 4]:
            raise ValueError(f"cell_num inválido: {cell_num}")
        suffix = "Inv" if inverse else ""
        return f"C{cell_num}{suffix}", f"C{cell_num}d{suffix}"
    def box_place_inverse_from_rack(self, cell_num: int) -> bool:
        """Orientación correcta al colocar desde rack a caja.

        Convención: una celda bien guardada en rack, cogida directamente del
        rack y colocada sin inverso, deja el lado rojo a la derecha.

        En la caja:
            - C1 y C3 usan place normal.
            - C2 y C4 usan place inverso.
        """
        if cell_num not in [1, 2, 3, 4]:
            raise ValueError(f"cell_num inválido: {cell_num}")
        return cell_num in [2, 4]
    def box_pick_inverse_to_store_in_rack(self, cell_num: int, polarity_ok: Optional[bool]) -> bool:
        """Pick para sacar una celda de la caja y guardarla en rack siempre igual.

        Objetivo del rack: todas las celdas deben quedar con la misma polaridad
        estándar. Según tu convención, si una celda se coge del rack y se coloca
        en caja sin inverso, queda con el lado rojo a la derecha.

        Regla exacta para SACAR de caja y guardar en rack:
            C1/C3 + polaridad OK  -> pick normal
            C1/C3 + polaridad BAD -> pick inverso
            C2/C4 + polaridad OK  -> pick inverso
            C2/C4 + polaridad BAD -> pick normal

        Si polarity_ok es None, se asume la geometría normal del hueco:
        C1/C3 normal y C2/C4 inverso.
        """
        if cell_num not in [1, 2, 3, 4]:
            raise ValueError(f"cell_num inválido: {cell_num}")

        # C1/C3 OK => normal. C2/C4 OK => inverso.
        inverse_when_ok = cell_num in [2, 4]

        if polarity_ok is False:
            return not inverse_when_ok
        return inverse_when_ok
    def place_cell_from_rack(self, cell_num: int, box_slot: int) -> bool:
        """Coloca en caja una celda que viene del rack con polaridad estándar."""
        inverse = self.box_place_inverse_from_rack(cell_num)
        return self.place_cell(cell_num, box_slot, inverse=inverse, source="rack")
    def pick_cell(
        self,
        cell_num: int,
        box_slot: int,
        inverse: bool = False,
        via_place_cell: bool = True,
    ) -> bool:
        self.lock_visual_updates(f"pick_cell Box{box_slot} C{cell_num}")

        try:
            target, target_down = self.cell_targets(cell_num, inverse=inverse)

            return self.sequence(
                f"[PickCell] Box{box_slot} C{cell_num} inverse={inverse}",
                # Use the entry waypoint only when arriving from outside this box path.
                lambda: self.movej_target("PlaceCell") if via_place_cell else True,
                lambda: self.set_box_frame(box_slot),
                self.grippercellopen,
                lambda: self.movej_target(target),
                lambda: self.movel_target(target_down),
                self.grippercellclose,
                # Registrar la última pieza pickeada (por id físico) en memoria
                lambda bs=box_slot, cn=cell_num: self._record_last_picked_from_box(bs, cn),
                lambda: self.movel_target(target),
                lambda: self.wait_move(f"PickCell Box{box_slot} C{cell_num}"),
            )

        finally:
            self.unlock_visual_updates(f"pick_cell Box{box_slot} C{cell_num} finalizado")
    def place_cell(self, cell_num: int, box_slot: int, inverse: bool = False, source: str = "box") -> bool:
        self.lock_visual_updates(f"place_cell Box{box_slot} C{cell_num}")

        try:
            target, target_down = self.cell_targets(cell_num, inverse=inverse)

            return self.sequence(
                f"[PlaceCell] Box{box_slot} C{cell_num} inverse={inverse} source={source}",
                lambda: self.set_box_frame(box_slot),
                lambda: self.movej_target(target),
                lambda: self.movel_target_with_local_z_offset(
                    target_down,
                    CELL_PLACE_DOWN_Z_OFFSET_MM,
                    context=f"{target_down}+Z{CELL_PLACE_DOWN_Z_OFFSET_MM:.1f}mm",
                ),
                self.grippercellopen,
                # Ajustar en el gemelo RoboDK la altura Z de la celda colocada (usar id real si lo conocemos)
                lambda bs=box_slot, cn=cell_num: self._apply_last_picked_visual_z(bs, cn, 508.616),
                lambda: self.movel_target(target),
                lambda: self.wait_move(f"PlaceCell Box{box_slot} C{cell_num}"),
            )

        finally:
            self.unlock_visual_updates(f"place_cell Box{box_slot} C{cell_num} finalizado")
    def rot_cell(self, cell_num: int, box_slot: int, via_place_cell: bool = True) -> bool:
        pick_inverse = self.box_pick_inverse_to_store_in_rack(cell_num, polarity_ok=False)
        place_inverse = self.box_place_inverse_from_rack(cell_num)
        return self.sequence(
            f"[RotCell] Box{box_slot} C{cell_num} pick_inverse={pick_inverse} place_inverse={place_inverse}",
            lambda: self.pick_cell(
                cell_num,
                box_slot,
                inverse=pick_inverse,
                via_place_cell=via_place_cell,
            ),
            lambda: self.place_cell(cell_num, box_slot, inverse=place_inverse, source="rot"),
        )

    def _record_last_picked_from_box(self, box_slot: int, cell_num: int) -> bool:
        try:
            box = self.boxes.get(int(box_slot), {}) or {}
            cells = box.get("cells", []) or []
            stored = cells[int(cell_num) - 1] if len(cells) >= int(cell_num) else None
            if isinstance(stored, dict) and stored.get("id"):
                self.last_picked_object_id = stored.get("id")
            else:
                self.last_picked_object_id = physical_cell_id_from_box_position(int(box_slot), int(cell_num))
            print(f"[Memory] last_picked_object_id = {self.last_picked_object_id}")
            return True
        except Exception as exc:
            print(f"[Memory][AVISO] No se pudo registrar last_picked desde Box{box_slot}C{cell_num}: {exc}")
            return False

    def _record_last_picked_from_rack(self, rack_slot: int) -> bool:
        try:
            cell = None
            if int(rack_slot) in self.rack_cells:
                cell = self.rack_cells[int(rack_slot)].get("cell")
            if isinstance(cell, dict) and cell.get("id"):
                self.last_picked_object_id = cell.get("id")
            else:
                self.last_picked_object_id = None
            print(f"[Memory] last_picked_object_id (rack) = {self.last_picked_object_id}")
            return True
        except Exception as exc:
            print(f"[Memory][AVISO] No se pudo registrar last_picked desde rack cell{rack_slot}: {exc}")
            return False

    def _apply_last_picked_visual_z(self, box_slot: int, cell_num: int, z_mm: float) -> bool:
        try:
            obj_id = getattr(self, "last_picked_object_id", None)
            if obj_id:
                return self.set_visual_z_for_object(obj_id, float(z_mm))

            # fallback: usar id por posicion base
            fallback = physical_cell_id_from_box_position(int(box_slot), int(cell_num))
            return self.set_visual_z_for_object(fallback, float(z_mm))
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo aplicar Z visual para Box{box_slot}C{cell_num}: {exc}")
            return False
    def pick_cell_rack(self, rack_cell_slot: Optional[int] = None, color: Optional[str] = None) -> Optional[Dict[str, Any]]:
        self.lock_visual_updates(f"pick_cell_rack cell{rack_cell_slot if rack_cell_slot is not None else color}")

        try:
            if rack_cell_slot is None:
                rack_cell_slot = self.find_rack_cell_by_color(color)

            if rack_cell_slot is None:
                print(f"[PickCellRack] No hay celda disponible en rack para color={color}")
                return None

            ok = self.sequence(
                f"[PickCellRack] cell{rack_cell_slot}",
                # Si existe target PrepareCell en RoboDK, pasar por él antes de coger del rack
                lambda: self.movej_target_if_exists("PrepareCell"),
                lambda: self.set_cell_frame(rack_cell_slot),
                self.grippercellopen,
                lambda: self.movej_target("pos"),
                lambda: self.movel_target("go"),
                self.grippercellclose,
                # Registrar última pieza pickeada desde rack (id almacenada en rack_cells)
                lambda slot=rack_cell_slot: self._record_last_picked_from_rack(slot),
                lambda: self.movel_target("up"),
                lambda: self.movel_target("out"),
                lambda: self.movej_target("PlaceCell"),
            )

            return self.remove_cell_from_rack(rack_cell_slot) if ok else None

        finally:
            self.unlock_visual_updates("pick_cell_rack finalizado")
    def place_cell_rack(self, color: str, rack_cell_slot: Optional[int] = None, extra: Optional[Dict[str, Any]] = None) -> Optional[int]:
        self.lock_visual_updates(f"place_cell_rack color={color}")

        try:
            if color not in VALID_COLORS:
                print(f"[PlaceCellRack][ERROR] Color inválido: {color}")
                return None

            rack_cell_slot = rack_cell_slot or self.find_free_rack_cell_slot(color)

            if rack_cell_slot is None:
                print(f"[PlaceCellRack][AVISO] No hay hueco libre para color={color}")
                return None

            expected_color = RACK_CELL_EXPECTED_COLOR.get(rack_cell_slot)
            if expected_color != color:
                print(
                    f"[PlaceCellRack][ERROR] No muevo: cell{rack_cell_slot} "
                    f"espera {expected_color}, recibido {color}"
                )
                return None

            ok = self.sequence(
                f"[PlaceCellRack] Guardando celda {color} en cell{rack_cell_slot}",
                lambda: self.set_cell_frame(rack_cell_slot),
                lambda: self.movej_target("PlaceCell"),
                lambda: self.movej_target("out"),
                lambda: self.movel_target("up"),
                lambda: self.movel_target("go"),
                self.grippercellopen,
                lambda: self.movel_target("pos"),
                lambda: self.movej_target("PlaceCell"),
            )

            if ok and self.store_cell_in_rack(rack_cell_slot, color, extra=extra):
                return rack_cell_slot

            return None

        finally:
            self.unlock_visual_updates("place_cell_rack finalizado")
    def camera_active_open_box(self, results: Dict[str, Any]) -> Optional[Tuple[int, Dict[str, Any]]]:
        if self.active_box_slot is None:
            self.reset_open_box_confirmation()
            return None

        slot_state = results.get(rack_slot_id(self.active_box_slot), {}) or {}
        if not slot_state.get("box_present", False):
            print(f"[Cells] Box{self.active_box_slot}: la cámara no ve caja presente")
            return None
        if not slot_state.get("confirmed_open", False):
            print(f"[Cells] Box{self.active_box_slot}: esperando caja abierta confirmada")
            return None

        return self.active_box_slot, slot_state
    def open_box_confirmation_signature_from_slot_state(self, slot_state: Dict[str, Any]) -> Tuple[Any, ...]:
        batteries = slot_state.get("battery_slots", {}) or {}
        battery_signature = tuple(
            (
                battery_id,
                bool((batteries.get(battery_id, {}) or {}).get("battery_present", False)),
                (batteries.get(battery_id, {}) or {}).get("battery_color", None),
                (batteries.get(battery_id, {}) or {}).get("polarity_ok", None),
            )
            for battery_id in BATTERY_SLOT_IDS
        )
        return (
            bool(slot_state.get("box_present", False)),
            bool(slot_state.get("confirmed_open", False)),
            slot_state.get("open_box_color", None),
            battery_signature,
        )
    def lid_collected_elapsed_s(self, box_slot: int) -> float:
        lid_collected_at = (self.boxes.get(box_slot, {}) or {}).get("lid_collected_at")
        if not lid_collected_at:
            return 0.0
        try:
            return max(0.0, time.time() - datetime.fromisoformat(lid_collected_at).timestamp())
        except Exception:
            return 0.0
    def active_open_box_vision_confirmed(
        self,
        box_slot: int,
        slot_state: Dict[str, Any],
        *,
        min_stable_s: float = OPEN_BOX_VISION_CONFIRMATION_S,
    ) -> bool:
        lid_elapsed = self.lid_collected_elapsed_s(box_slot)

        if lid_elapsed < min_stable_s:
            print(
                f"[VisionConfirm] Box{box_slot}: esperando tras retirar tapa "
                f"{lid_elapsed:.1f}/{min_stable_s:.1f}s"
            )
            print(f"[VisionConfirm] Box{box_slot}: iniciando confirmaciÃ³n estable ({min_stable_s:.1f}s)")
            return False

        if False:
            self.open_box_confirmation_signature = signature
            self.open_box_confirmation_since = now
            print(f"[VisionConfirm] Box{box_slot}: cambios detectados, reinicio confirmaciÃ³n ({min_stable_s:.1f}s)")
            return False

        stable_elapsed = min_stable_s
        if stable_elapsed < min_stable_s:
            print(
                f"[VisionConfirm] Box{box_slot}: esperando visiÃ³n estable "
                f"{stable_elapsed:.1f}/{min_stable_s:.1f}s"
            )
            return False

        return True
    def set_box_cell(self, box_slot: int, cell_num: int, cell_data: Optional[Dict[str, Any]]) -> None:
        self.boxes[box_slot]["cells"][cell_num - 1] = deepcopy(cell_data)
    def known_or_detected_cell(self, box_slot: int, cell_num: int, color: str, polarity_ok: Optional[bool]) -> Dict[str, Any]:
        """Devuelve la pieza física que hay en BoxN Cn.

        Si ya estaba en memoria, conserva su ID real. Si viene de una detección
        inicial de cámara, crea el ID físico base S01..S12 según la posición.
        """
        stored = self.boxes[box_slot]["cells"][cell_num - 1]
        if isinstance(stored, dict) and stored.get("id"):
            cell = deepcopy(stored)
            if self.boxes[box_slot].get("initial_cells_captured", False) and cell.get("color") in VALID_COLORS:
                color = cell["color"]
        else:
            cell = {
                "id": physical_cell_id_from_box_position(box_slot, cell_num),
                "created_from_camera": True,
            }

        cell["color"] = color
        cell["polarity_ok"] = polarity_ok
        cell["location"] = f"Box{box_slot}C{cell_num}"
        cell["updated_at"] = now_iso()
        return cell
    def mark_cell_in_box(
        self,
        box_slot: int,
        cell_num: int,
        cell: Dict[str, Any],
        *,
        ok: bool,
        source: str,
        polarity_ok: Optional[bool] = True,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        cell_obj = deepcopy(cell)
        cell_obj["ok"] = bool(ok)
        cell_obj["source"] = source
        cell_obj["polarity_ok"] = polarity_ok
        cell_obj["location"] = f"Box{box_slot}C{cell_num}"
        cell_obj["updated_at"] = now_iso()
        if extra:
            cell_obj.update(extra)
        self.set_box_cell(box_slot, cell_num, cell_obj)
    def box_complete(self, box_slot: int) -> bool:
        cells = self.boxes[box_slot]["cells"]
        return len(cells) == 4 and all(isinstance(c, dict) and c.get("ok") is True for c in cells)
