"""Live RoboDK visual updater for station objects.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from math import degrees, radians
from typing import Optional

import numpy as np

from app_config import *
from object_names import battery_object_names
from robodk_compat import *

class RoboDKLiveUpdater:
    """Actualiza el gemelo digital de RoboDK con una memoria visual simple por slot."""

    VALID_COLORS = ("red", "green", "blue")
    OPEN_MEMORY_STATES = {
        "open_waiting_cells",
        "processing_cells",
        "waiting_rack_cells",
        "cells_complete",
        "cells_complete_waiting_lid",
    }
    FINAL_MEMORY_STATES = {"closed_complete", "finished"}

    def __init__(self):
        if Robolink is None:
            raise ImportError("No se pudo importar RoboDK API. Instala con: python -m pip install robodk")

        self.rdk = Robolink()
        self.station_logic = None
        self.visual_updates_locked = False
        self.lock_cell_updates = False
        self.robot_red_zone_active = False
        self.frozen_slot_id = None
        self.cache = {}
        self.original_poses = {}
        self.original_abs_poses = {}
        self.warned_missing = set()
        self.visibility_state = {}
        self.pose_state = {}
        self.bridge_visual_fixed = {}
        self.current_bridge_state = {"pieces": []}
        self.live_bridge_visuals = {}
        self.slots = {slot_id: self.new_slot_state() for slot_id in RACK_SLOT_IDS}

        self.preload_items()
        self.hide_everything()

    def new_slot_state(self):
        return {
            "phase": "empty",
            "locked_final": False,
            "lid_color": None,
            "lid_locked": False,
            "lid_owned_by_slot": False,
            "box_color": None,
            "box_locked": False,
            "cells_released": False,
            "cells": {
                battery_slot_id: {
                    "visible": False,
                    "color": None,
                    "polarity_ok": None,
                    "color_locked": False,
                }
                for battery_slot_id in BATTERY_SLOT_IDS
            },
        }

    def bind_station_logic(self, station_logic):
        self.station_logic = station_logic

    def get_item(self, name, force_refresh=False):
        if not force_refresh and name in self.cache:
            return self.cache[name]

        item = self.rdk.Item(name, ITEM_TYPE_OBJECT)
        if not item.Valid() and name not in self.warned_missing:
            print(f"[RoboDK][AVISO] No existe el objeto: {name}")
            self.warned_missing.add(name)

        self.cache[name] = item
        return item

    def refresh_item(self, name):
        self.cache.pop(name, None)
        self.visibility_state.pop(name, None)
        self.pose_state.pop(name, None)
        if name in self.original_poses:
            self.original_poses.pop(name, None)
        if name in self.original_abs_poses:
            self.original_abs_poses.pop(name, None)
        return self.get_item(name, force_refresh=True)

    def refresh_all_items(self):
        self.cache.clear()
        self.visibility_state.clear()
        self.pose_state.clear()
        self.original_poses.clear()
        self.original_abs_poses.clear()
        self.warned_missing.clear()
        self.preload_items()

    def set_visible(self, name, visible):
        visible = bool(visible)
        if self.visibility_state.get(name) == visible:
            return

        item = self.get_item(name)
        if item.Valid():
            try:
                item.setVisible(visible)
                self.visibility_state[name] = visible
            except Exception as exc:
                print(f"[RoboDK][AVISO] setVisible fallo para {name}: {exc}. Reintentando con refresh...")
                item = self.refresh_item(name)
                if item.Valid():
                    try:
                        item.setVisible(visible)
                        self.visibility_state[name] = visible
                    except Exception as exc_retry:
                        print(f"[RoboDK][ERROR] setVisible sigue fallando para {name}: {exc_retry}")

    def save_original_pose(self, name):
        item = self.get_item(name)
        if item.Valid() and name not in self.original_poses:
            try:
                self.original_poses[name] = item.Pose()
            except Exception as exc:
                print(f"[RoboDK][AVISO] No se pudo guardar pose original de {name}: {exc}")

    def save_original_abs_pose(self, name):
        item = self.get_item(name)
        if item.Valid() and name not in self.original_abs_poses:
            try:
                if hasattr(item, "PoseAbs"):
                    self.original_abs_poses[name] = item.PoseAbs()
                else:
                    self.original_abs_poses[name] = item.Pose()
            except Exception as exc:
                print(f"[RoboDK][AVISO] No se pudo guardar pose absoluta original de {name}: {exc}")

    def set_pose_with_global_z_offset_from_original(self, name, z_offset_mm):
        item = self.get_item(name)
        if not item.Valid() or Pose_2_TxyzRxyz is None or TxyzRxyz_2_Pose is None:
            return

        self.save_original_abs_pose(name)
        base_pose = self.original_abs_poses.get(name)
        if base_pose is None:
            return

        try:
            xyzrxyz = list(Pose_2_TxyzRxyz(base_pose))
            xyzrxyz[2] = float(xyzrxyz[2]) + float(z_offset_mm)
            offset_pose = TxyzRxyz_2_Pose(xyzrxyz)
            if hasattr(item, "setPoseAbs"):
                item.setPoseAbs(offset_pose)
            else:
                item.setPose(offset_pose)
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo aplicar offset global Z a {name}: {exc}")

    def set_item_global_z(self, name: str, z_mm: float) -> bool:
        """Setea la coordenada Z absoluta global de un objeto, manteniendo X/Y/Rx/Ry/Rz.

        Devuelve True si se aplicó correctamente o False en fallo.
        """
        item = self.get_item(name)
        if not item.Valid() or Pose_2_TxyzRxyz is None or TxyzRxyz_2_Pose is None:
            return False

        try:
            # Usar pose absoluta si está disponible
            base_pose = item.PoseAbs() if hasattr(item, "PoseAbs") else item.Pose()
            xyzrxyz = list(Pose_2_TxyzRxyz(base_pose))
            xyzrxyz[2] = float(z_mm)
            new_pose = TxyzRxyz_2_Pose(xyzrxyz)
            if hasattr(item, "setPoseAbs"):
                item.setPoseAbs(new_pose)
            else:
                item.setPose(new_pose)
            # invalidate cached pose state
            self.pose_state.pop(name, None)
            return True
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo mover {name} a Z={z_mm}: {exc}")
            return False

    def rotated_pose(self, base_pose):
        axis = POLARITY_ROTATION_AXIS.upper()
        if axis == "X":
            return base_pose * rotx(np.pi)
        if axis == "Y":
            return base_pose * roty(np.pi)
        return base_pose * rotz(np.pi)

    @staticmethod
    def pose_with_current_position(item, orientation_pose, use_absolute_pose):
        """Keep current XYZ while applying the required object orientation."""
        current_pose = item.PoseAbs() if use_absolute_pose and hasattr(item, "PoseAbs") else item.Pose()
        current_xyzrxyz = list(Pose_2_TxyzRxyz(current_pose))
        desired_xyzrxyz = list(Pose_2_TxyzRxyz(orientation_pose))
        desired_xyzrxyz[:3] = current_xyzrxyz[:3]
        return TxyzRxyz_2_Pose(desired_xyzrxyz)

    def set_pose_by_polarity(self, name, polarity_ok):
        item = self.get_item(name)
        if not item.Valid():
            return

        desired_pose_state = "inverted" if polarity_ok is False else "original"
        if self.pose_state.get(name) == desired_pose_state:
            return
        # Preferir la pose absoluta guardada si existe; usar setPoseAbs para
        # que cambios de parent/frame no desplacen el objeto.
        self.save_original_pose(name)
        self.save_original_abs_pose(name)

        base_pose_abs = self.original_abs_poses.get(name)
        base_pose_local = self.original_poses.get(name)

        if base_pose_abs is None and base_pose_local is None:
            return

        try:
            use_absolute_pose = base_pose_abs is not None and hasattr(item, "setPoseAbs")
            orientation_base = base_pose_abs if use_absolute_pose else base_pose_local
            if orientation_base is None:
                orientation_base = base_pose_abs
            desired_pose = self.rotated_pose(orientation_base) if desired_pose_state == "inverted" else orientation_base
            desired_pose = self.pose_with_current_position(item, desired_pose, use_absolute_pose)

            # Preferir setPoseAbs cuando esté disponible y tengamos una pose absoluta.
            if use_absolute_pose:
                item.setPoseAbs(desired_pose)
            else:
                item.setPose(desired_pose)

            self.pose_state[name] = desired_pose_state
        except Exception as exc:
            print(f"[RoboDK][AVISO] setPose fallo para {name}: {exc}. Reintentando con refresh...")
            item = self.refresh_item(name)
            if not item.Valid():
                return
            # intentar de nuevo con las poses guardadas
            base_pose_abs = self.original_abs_poses.get(name)
            base_pose_local = self.original_poses.get(name)
            if base_pose_abs is None and base_pose_local is None:
                return
            try:
                use_absolute_pose = base_pose_abs is not None and hasattr(item, "setPoseAbs")
                orientation_base = base_pose_abs if use_absolute_pose else base_pose_local
                if orientation_base is None:
                    orientation_base = base_pose_abs
                desired_pose = self.rotated_pose(orientation_base) if desired_pose_state == "inverted" else orientation_base
                desired_pose = self.pose_with_current_position(item, desired_pose, use_absolute_pose)
                if use_absolute_pose:
                    item.setPoseAbs(desired_pose)
                else:
                    item.setPose(desired_pose)
                self.pose_state[name] = desired_pose_state
            except Exception as exc_retry:
                print(f"[RoboDK][ERROR] setPose sigue fallando para {name}: {exc_retry}")

    def preload_items(self):
        for slot_id in RACK_SLOT_IDS:
            for name in LID_OBJECTS[slot_id].values():
                self.get_item(name)

            for name in BOX_OBJECTS[slot_id].values():
                self.get_item(name)

            for battery_slot_id in BATTERY_SLOT_IDS:
                for name in battery_object_names(slot_id, battery_slot_id).values():
                    self.get_item(name)
                    # Guardar tanto la pose local original como la absoluta. Usar la
                    # absoluta posteriormente evita que cambios de parent/frame
                    # muevan la visual cuando no se toca el objeto.
                    self.save_original_pose(name)
                    self.save_original_abs_pose(name)

        if ITEM_TYPE_FRAME is not None:
            self.rdk.Item(BRIDGE_VISUAL_FRAME_NAME, ITEM_TYPE_FRAME)

        for box_slot in [1, 2, 3]:
            for piece_name in BRIDGE_VISUAL_OBJECTS.get(box_slot, {}).values():
                self.get_item(piece_name)
                self.save_original_pose(piece_name)
                self.save_original_abs_pose(piece_name)

    def set_visual_updates_locked(self, locked: bool, reason: str = ""):
        locked = bool(locked)
        if self.visual_updates_locked == locked:
            return

        self.visual_updates_locked = locked
        text = "BLOQUEADO" if locked else "DESBLOQUEADO"
        print(f"[RoboDKLiveUpdater] Visual update {text}: {reason}")

    def set_cell_updates_locked(self, locked: bool):
        self.lock_cell_updates = bool(locked)
        self.set_visual_updates_locked(locked, "cell/lid interaction")

    def current_freezable_slot_id(self):
        if self.station_logic is None:
            return None

        active_box_slot = getattr(self.station_logic, "active_box_slot", None)
        if active_box_slot not in RACK_TO_NUMBER.values():
            return None

        boxes = getattr(self.station_logic, "boxes", {}) or {}
        box = boxes.get(active_box_slot, {}) or {}
        if not bool(box.get("lid_collected", False)):
            return None

        if box.get("state") not in {"open_waiting_cells", "processing_cells", "waiting_rack_cells"}:
            return None

        return f"rack_slot_{active_box_slot}"

    def set_robot_red_zone(self, in_red_zone: bool):
        in_red_zone = bool(in_red_zone)
        if self.robot_red_zone_active == in_red_zone:
            return

        self.robot_red_zone_active = in_red_zone
        if in_red_zone:
            self.frozen_slot_id = self.current_freezable_slot_id()
            if self.frozen_slot_id is not None:
                print(f"[RoboDKLiveUpdater] Congelando slot activo por zona roja: {self.frozen_slot_id}")
            else:
                print("[RoboDKLiveUpdater] Zona roja sin slot activo congelable.")
            return

        if self.frozen_slot_id is not None:
            print(f"[RoboDKLiveUpdater] Reanudando actualizacion en directo: {self.frozen_slot_id}")
        self.frozen_slot_id = None

    def is_valid_color(self, color):
        return color in self.VALID_COLORS

    def lid_claimed_by_other_box(self, lid_name, current_slot_id):
        for other_slot_id in RACK_SLOT_IDS:
            if other_slot_id == current_slot_id:
                continue
            box = self.station_box_memory(other_slot_id)
            if not isinstance(box, dict):
                continue
            if (
                box.get("present", False)
                and not box.get("lid_collected", False)
                and box.get("lid_visual_name") == lid_name
            ):
                return True
        if self.station_logic is not None:
            for lid_slot in (getattr(self.station_logic, "lid_slots", {}) or {}).values():
                stored = (lid_slot or {}).get("stored")
                if isinstance(stored, dict) and stored.get("visual_name") == lid_name:
                    return True
            for picked in getattr(self.station_logic, "picked_lids", []) or []:
                if isinstance(picked, dict) and picked.get("visual_name") == lid_name:
                    return True
        return False

    def hide_lids(self, slot_id):
        for name in LID_OBJECTS[slot_id].values():
            if not self.lid_claimed_by_other_box(name, slot_id):
                self.set_visible(name, False)

    def lid_visual_name(self, box_slot, lid_color):
        return (LID_OBJECTS.get(f"rack_slot_{int(box_slot)}", {}) or {}).get(lid_color)

    def simulate_lid_gravity_drop_on_box(self, box_slot, lid_color, visual_name: Optional[str] = None):
        if lid_color not in self.VALID_COLORS:
            print(f"[RoboDK][LidGravity][AVISO] Color de tapa no valido: {lid_color}")
            return False

        pose_data = LID_GRAVITY_DROP_GLOBAL_POSES.get(int(box_slot))
        if not isinstance(pose_data, dict):
            print(f"[RoboDK][LidGravity][AVISO] No hay pose de gravedad para Box{box_slot}")
            return False

        # Preferir el nombre visual proporcionado por la memoria (visual_name),
        # si se entregó; sino usar la convención por slot/colour.
        lid_name = visual_name if visual_name else self.lid_visual_name(box_slot, lid_color)
        if not lid_name:
            print(f"[RoboDK][LidGravity][AVISO] No encuentro objeto lid para Box{box_slot} color {lid_color}")
            return False

        item = self.get_item(lid_name)
        if not item.Valid() or TxyzRxyz_2_Pose is None:
            print(f"[RoboDK][LidGravity][AVISO] Objeto lid no valido: {lid_name}")
            return False

        xyzrxyz = [
            float(pose_data["x"]),
            float(pose_data["y"]),
            float(pose_data["z"]),
            0.0,
            0.0,
            radians(float(pose_data.get("rz_deg", 0.0))),
        ]

        try:
            pose = TxyzRxyz_2_Pose(xyzrxyz)
            if hasattr(item, "setPoseAbs"):
                item.setPoseAbs(pose)
            else:
                item.setPose(pose)

            self.pose_state.pop(lid_name, None)
            self.set_visible(lid_name, True)
            slot_id = f"rack_slot_{int(box_slot)}"
            if slot_id in self.slots:
                self.slots[slot_id]["lid_color"] = lid_color
                self.slots[slot_id]["lid_locked"] = True
                self.slots[slot_id]["lid_owned_by_slot"] = True
            print(
                f"[RoboDK][LidGravity] {lid_name} soltada en Box{box_slot}: "
                f"X={xyzrxyz[0]:.2f}, Y={xyzrxyz[1]:.2f}, Z={xyzrxyz[2]:.2f}, "
                f"Rz={pose_data.get('rz_deg', 0.0):.1f}deg"
            )
            return True
        except Exception as exc:
            print(f"[RoboDK][LidGravity][AVISO] No se pudo mover {lid_name}: {exc}")
            return False

    def release_lid_from_slot(self, box_slot, visual_name: Optional[str] = None):
        slot_id = f"rack_slot_{int(box_slot)}"
        slot = self.slots.get(slot_id)
        if isinstance(slot, dict):
            slot["lid_owned_by_slot"] = False
        if visual_name:
            print(f"[RoboDK][LidMemory] {visual_name} liberada de Box{box_slot} por pick real.")

    def reopen_completed_box_from_station(self, box_slot):
        """Render a completed donor box as open after its lid is reused."""
        slot_id = f"rack_slot_{int(box_slot)}"
        slot = self.slots.get(slot_id)
        if not isinstance(slot, dict):
            return False

        slot["locked_final"] = False
        slot["phase"] = "open"
        slot["lid_owned_by_slot"] = False
        slot["cells_released"] = True

        box_color = self.station_box_color(slot_id)
        if self.is_valid_color(box_color):
            self.lock_box(slot_id, box_color)

        self.render_slot(slot_id)
        self.update_bridge_visuals()
        print(f"[RoboDK][LidMemory] Box{box_slot} reabierta desde memoria tras reutilizar su tapa.")
        return True

    def hide_boxes(self, slot_id):
        for name in BOX_OBJECTS[slot_id].values():
            self.set_visible(name, False)

    def hide_one_battery(self, slot_id, battery_slot_id):
        for name in battery_object_names(slot_id, battery_slot_id).values():
            self.set_visible(name, False)

    def hide_batteries(self, slot_id):
        for battery_slot_id in BATTERY_SLOT_IDS:
            self.hide_one_battery(slot_id, battery_slot_id)

    def hide_slot(self, slot_id):
        self.hide_lids(slot_id)
        self.hide_boxes(slot_id)
        self.hide_batteries(slot_id)

    def hide_everything(self):
        for slot_id in RACK_SLOT_IDS:
            self.hide_slot(slot_id)
        self.hide_bridge_visuals()

    def get_frame(self, name):
        if ITEM_TYPE_FRAME is None:
            return self.rdk.Item(name)
        return self.rdk.Item(name, ITEM_TYPE_FRAME)

    def bridge_visual_name(self, box_slot, piece_type):
        return (BRIDGE_VISUAL_OBJECTS.get(box_slot, {}) or {}).get(piece_type)

    def bridge_visual_slots_by_type(self, piece_type):
        slots = []
        for box_slot in [1, 2, 3]:
            piece_name = self.bridge_visual_name(box_slot, piece_type)
            if piece_name:
                slots.append((box_slot, piece_name))
        return slots

    def current_bridge_pieces_by_type(self, piece_type):
        bridge_state = self.current_bridge_state or {}
        pieces = bridge_state.get("pieces", [])
        if not isinstance(pieces, list):
            return []

        filtered = [
            piece
            for piece in pieces
            if isinstance(piece, dict)
            and piece.get("type") == piece_type
            and piece.get("inside_homography", True)
        ]
        filtered.sort(
            key=lambda piece: (
                self._bridge_piece_number(piece, "center_x_mm", "center_x_rdk_mm"),
                self._bridge_piece_number(piece, "center_y_mm", "center_y_rdk_mm"),
                -self._bridge_piece_number(piece, "confidence"),
            )
        )
        return filtered

    def bridge_piece_seen_now(self, piece_type):
        return bool(self.current_bridge_pieces_by_type(piece_type))

    def bridge_pick_target_name(self, piece_type):
        return BRIDGE_PICK_TARGET_BY_TYPE.get(piece_type)

    def get_bridge_pick_target(self, piece_type):
        target_name = self.bridge_pick_target_name(piece_type)
        if not target_name:
            return None
        if ITEM_TYPE_TARGET is None:
            return self.rdk.Item(target_name)
        return self.rdk.Item(target_name, ITEM_TYPE_TARGET)

    def hide_bridge_visuals(self):
        self.bridge_visual_fixed.clear()
        self.live_bridge_visuals.clear()
        for box_slot in [1, 2, 3]:
            for piece_name in BRIDGE_VISUAL_OBJECTS.get(box_slot, {}).values():
                self.set_visible(piece_name, False)

    def bridge_memory(self, box_slot, piece_type):
        box = self.station_box_memory(f"rack_slot_{box_slot}")
        if not isinstance(box, dict):
            return None
        piece = (box.get("bridge_parts_info", {}) or {}).get(piece_type)
        if isinstance(piece, dict):
            return piece
        return None

    def bridge_piece_done(self, box_slot, piece_type):
        box = self.station_box_memory(f"rack_slot_{box_slot}")
        if not isinstance(box, dict):
            return False
        return bool((box.get("bridge_parts_done", {}) or {}).get(piece_type, False))

    def bridge_box_active_for_visual(self, box_slot):
        box = self.station_box_memory(f"rack_slot_{box_slot}")
        if not isinstance(box, dict):
            return False
        return box.get("state") in {"bridges_pending", "bridge_ready"}

    def bridge_box_present(self, box_slot):
        box = self.station_box_memory(f"rack_slot_{box_slot}")
        if not isinstance(box, dict):
            return False
        return bool(box.get("present", False))

    def attach_item_to_frame_without_moving(self, item, frame):
        if not item.Valid() or not frame.Valid():
            return False

        try:
            absolute_pose = item.PoseAbs() if hasattr(item, "PoseAbs") else item.Pose()
        except Exception:
            absolute_pose = None

        try:
            if hasattr(item, "setParentStatic"):
                item.setParentStatic(frame)
            else:
                item.setParent(frame)
                if absolute_pose is not None:
                    if hasattr(item, "setPoseAbs"):
                        item.setPoseAbs(absolute_pose)
                    else:
                        item.setPose(absolute_pose)
            return True
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo adjuntar objeto a {frame.Name()}: {exc}")
            return False

    def set_bridge_piece_pose_from_pick_target(self, box_slot, piece_type, mark_fixed=False):
        piece_name = self.bridge_visual_name(box_slot, piece_type)
        target_name = self.bridge_pick_target_name(piece_type)
        if not piece_name or not target_name:
            return False

        item = self.get_item(piece_name)
        bridge_frame = self.get_frame(BRIDGE_FRAME_NAME)
        pick_target = self.get_bridge_pick_target(piece_type)
        if (
            not item.Valid()
            or not bridge_frame.Valid()
            or pick_target is None
            or not pick_target.Valid()
            or Pose_2_TxyzRxyz is None
            or TxyzRxyz_2_Pose is None
        ):
            return False

        try:
            self.attach_item_to_frame_without_moving(item, bridge_frame)

            target_xyzrxyz = list(Pose_2_TxyzRxyz(pick_target.Pose()))
            object_xyzrxyz = list(Pose_2_TxyzRxyz(item.Pose()))

            # El target de pick ya contiene la correccion buena en el frame Bridge:
            # copiamos solo X/Y y Rz, dejando Z/Rx/Ry propios del objeto visual.
            final_xyzrxyz = list(object_xyzrxyz)
            final_xyzrxyz[0] = float(target_xyzrxyz[0])
            final_xyzrxyz[1] = float(target_xyzrxyz[1])
            visual_offset_rad = radians(float(BRIDGE_VISUAL_ROTATION_OFFSET_DEG))
            final_xyzrxyz[5] = float(target_xyzrxyz[5]) + visual_offset_rad

            item.setPose(TxyzRxyz_2_Pose(final_xyzrxyz))
            self.set_visible(piece_name, True)

            if mark_fixed:
                self.bridge_visual_fixed[(box_slot, piece_type)] = target_name

            print(
                f"[RoboDK][BridgeVisual] {piece_name} fijado desde {target_name} "
                f"en frame {BRIDGE_FRAME_NAME}: X={final_xyzrxyz[0]:.2f}, "
                f"Y={final_xyzrxyz[1]:.2f}, "
                f"target_Rz={degrees(float(target_xyzrxyz[5])):.2f}deg, "
                f"visual_Rz={degrees(float(final_xyzrxyz[5])):.2f}deg "
                f"(offset={BRIDGE_VISUAL_ROTATION_OFFSET_DEG:+.1f} deg)"
            )
            return True
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo fijar {piece_name} desde {target_name}: {exc}")
            return False

    @staticmethod
    def _bridge_piece_number(piece_info, *keys, default=0.0):
        for key in keys:
            try:
                value = piece_info.get(key)
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return float(default)

    def set_bridge_piece_pose_from_live_piece(self, box_slot, piece_type, piece_info):
        piece_name = self.bridge_visual_name(box_slot, piece_type)
        if not piece_name or not isinstance(piece_info, dict):
            return False

        item = self.get_item(piece_name)
        bridge_frame = self.get_frame(BRIDGE_FRAME_NAME)
        if (
            not item.Valid()
            or not bridge_frame.Valid()
            or Pose_2_TxyzRxyz is None
            or TxyzRxyz_2_Pose is None
        ):
            return False

        try:
            self.attach_item_to_frame_without_moving(item, bridge_frame)
            object_xyzrxyz = list(Pose_2_TxyzRxyz(item.Pose()))

            final_xyzrxyz = list(object_xyzrxyz)
            final_xyzrxyz[0] = self._bridge_piece_number(piece_info, "center_x_rdk_mm", "center_x_mm")
            final_xyzrxyz[1] = self._bridge_piece_number(piece_info, "center_y_rdk_mm", "center_y_mm")
            angle_deg = (
                self._bridge_piece_number(piece_info, "rotation_deg")
                * float(BRIDGE_VISUAL_ROTATION_SIGN)
                + float(BRIDGE_VISUAL_ROTATION_OFFSET_DEG)
            )
            final_xyzrxyz[5] = radians(float(angle_deg))

            item.setPose(TxyzRxyz_2_Pose(final_xyzrxyz))
            self.set_visible(piece_name, True)
            return True
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo mostrar {piece_name} desde vision bridge: {exc}")
            return False

    def bridge_live_pose_data(self, piece_info):
        return {
            "x": self._bridge_piece_number(piece_info, "center_x_rdk_mm", "center_x_mm"),
            "y": self._bridge_piece_number(piece_info, "center_y_rdk_mm", "center_y_mm"),
            "angle": self._bridge_piece_number(piece_info, "rotation_deg"),
        }

    @staticmethod
    def bridge_angle_delta_deg(angle_a, angle_b):
        delta = (float(angle_a) - float(angle_b) + 180.0) % 360.0 - 180.0
        return abs(delta)

    def bridge_live_distance_mm(self, assignment, piece_info):
        pose = self.bridge_live_pose_data(piece_info)
        dx = pose["x"] - float(assignment.get("x", 0.0))
        dy = pose["y"] - float(assignment.get("y", 0.0))
        return float(np.hypot(dx, dy))

    def bridge_live_pose_changed(self, assignment, piece_info):
        pose = self.bridge_live_pose_data(piece_info)
        distance = self.bridge_live_distance_mm(assignment, piece_info)
        angle_delta = self.bridge_angle_delta_deg(pose["angle"], assignment.get("angle", 0.0))
        return (
            distance >= float(BRIDGE_LIVE_VISUAL_MOVE_THRESHOLD_MM)
            or angle_delta >= float(BRIDGE_LIVE_VISUAL_ANGLE_THRESHOLD_DEG)
        )

    def remember_live_bridge_visual(self, piece_name, piece_type, piece_info):
        pose = self.bridge_live_pose_data(piece_info)
        self.live_bridge_visuals[piece_name] = {
            "piece_type": piece_type,
            "x": pose["x"],
            "y": pose["y"],
            "angle": pose["angle"],
            "missing_frames": 0,
        }

    def show_bridge_pick_visuals_from_targets(self, box_slot):
        ok = True
        for piece_type in BRIDGE_CLASSES:
            ok = self.set_bridge_piece_pose_from_pick_target(
                box_slot,
                piece_type,
                mark_fixed=True,
            ) and ok
        return ok

    def set_bridge_piece_pose(self, box_slot, piece_type, piece_info):
        if self.set_bridge_piece_pose_from_pick_target(box_slot, piece_type, mark_fixed=False):
            return

        piece_name = self.bridge_visual_name(box_slot, piece_type)
        if not piece_name or not isinstance(piece_info, dict):
            return

        item = self.get_item(piece_name)
        bridge_source = self.get_bridge_pick_target(piece_type)
        if (
            not item.Valid()
            or bridge_source is None
            or not bridge_source.Valid()
            or Pose_2_TxyzRxyz is None
            or TxyzRxyz_2_Pose is None
        ):
            return

        self.save_original_abs_pose(piece_name)
        original_abs_pose = self.original_abs_poses.get(piece_name)
        if original_abs_pose is None:
            return

        target_xyzrxyz = list(Pose_2_TxyzRxyz(bridge_source.PoseAbs()))
        object_xyzrxyz = list(Pose_2_TxyzRxyz(original_abs_pose))

        target_xyzrxyz[0] = float(target_xyzrxyz[0]) + float(piece_info.get("center_x_mm", 0.0))
        target_xyzrxyz[1] = float(target_xyzrxyz[1]) + float(piece_info.get("center_y_mm", 0.0))

        angle_deg = (
            float(piece_info.get("rotation_deg", 0.0)) * float(BRIDGE_VISUAL_ROTATION_SIGN)
            + float(BRIDGE_VISUAL_ROTATION_OFFSET_DEG)
        )
        target_xyzrxyz[5] = float(target_xyzrxyz[5]) + radians(float(angle_deg))

        final_xyzrxyz = list(object_xyzrxyz)
        final_xyzrxyz[0] = float(target_xyzrxyz[0])
        final_xyzrxyz[1] = float(target_xyzrxyz[1])
        final_xyzrxyz[3] = float(target_xyzrxyz[3])
        final_xyzrxyz[4] = float(target_xyzrxyz[4])
        final_xyzrxyz[5] = float(target_xyzrxyz[5])
        absolute_pose = TxyzRxyz_2_Pose(final_xyzrxyz)

        try:
            if hasattr(item, "setPoseAbs"):
                item.setPoseAbs(absolute_pose)
            else:
                item.setPose(absolute_pose)
            self.set_visible(piece_name, True)
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo colocar {piece_name} en Bridge: {exc}")

    def set_bridge_piece_pose_in_box(self, box_slot, piece_type):
        piece_name = self.bridge_visual_name(box_slot, piece_type)
        if not piece_name:
            return

        item = self.get_item(piece_name)
        box_frame = self.get_frame(f"Box{box_slot}")
        if not item.Valid() or not box_frame.Valid():
            return

        try:
            self.attach_item_to_frame_without_moving(item, box_frame)
            self.set_visible(piece_name, True)
        except Exception as exc:
            print(f"[RoboDK][AVISO] No se pudo colocar {piece_name} en Box{box_slot}: {exc}")

    """ def update_live_bridge_preview_visuals(self, reserved_visuals, reserved_live_counts):
        for piece_type in BRIDGE_CLASSES:
            pieces = self.current_bridge_pieces_by_type(piece_type)
            skip_count = int(reserved_live_counts.get(piece_type, 0))
            if skip_count > 0:
                pieces = pieces[skip_count:]

            available_visuals = [
                (box_slot, piece_name)
                for box_slot, piece_name in self.bridge_visual_slots_by_type(piece_type)
                if piece_name not in reserved_visuals
            ]
            matched_piece_indexes = set()
            active_visuals = set()

            for box_slot, piece_name in available_visuals:
                assignment = self.live_bridge_visuals.get(piece_name)
                if not assignment or assignment.get("piece_type") != piece_type:
                    continue

                best_idx = None
                best_distance = float("inf")
                for idx, piece_info in enumerate(pieces):
                    if idx in matched_piece_indexes:
                        continue
                    distance = self.bridge_live_distance_mm(assignment, piece_info)
                    if distance < best_distance:
                        best_distance = distance
                        best_idx = idx

                if (
                    best_idx is not None
                    and best_distance <= float(BRIDGE_LIVE_VISUAL_MATCH_THRESHOLD_MM)
                ):
                    piece_info = pieces[best_idx]
                    if self.bridge_live_pose_changed(assignment, piece_info):
                        self.set_bridge_piece_pose_from_live_piece(box_slot, piece_type, piece_info)
                        self.remember_live_bridge_visual(piece_name, piece_type, piece_info)
                    else:
                        assignment["missing_frames"] = 0
                        self.set_visible(piece_name, True)

                    matched_piece_indexes.add(best_idx)
                    active_visuals.add(piece_name)
                    reserved_visuals.add(piece_name)
                    continue

                assignment["missing_frames"] = int(assignment.get("missing_frames", 0)) + 1
                if assignment["missing_frames"] >= int(BRIDGE_LIVE_VISUAL_MISSING_FRAMES_TO_HIDE):
                    self.live_bridge_visuals.pop(piece_name, None)
                    self.set_visible(piece_name, False)
                else:
                    self.set_visible(piece_name, True)
                    active_visuals.add(piece_name)
                    reserved_visuals.add(piece_name)

            for idx, piece_info in enumerate(pieces):
                if idx in matched_piece_indexes:
                    continue

                visual_slot = None
                visual_name = None
                for box_slot, piece_name in available_visuals:
                    if piece_name in reserved_visuals or piece_name in active_visuals:
                        continue
                    visual_slot = box_slot
                    visual_name = piece_name
                    break

                if visual_slot is None or visual_name is None:
                    break

                if self.set_bridge_piece_pose_from_live_piece(visual_slot, piece_type, piece_info):
                    self.remember_live_bridge_visual(visual_name, piece_type, piece_info)
                    active_visuals.add(visual_name)
                    reserved_visuals.add(visual_name)

            for _, piece_name in available_visuals:
                if piece_name not in active_visuals and piece_name not in reserved_visuals:
                    self.live_bridge_visuals.pop(piece_name, None)
                    self.set_visible(piece_name, False)

        for piece_name in list(self.live_bridge_visuals.keys()):
            if piece_name not in reserved_visuals:
                self.live_bridge_visuals.pop(piece_name, None)"""

    def update_bridge_visuals(self):
        active_box_slot = getattr(self.station_logic, "active_box_slot", None)

        for box_slot in [1, 2, 3]:
            for piece_type in BRIDGE_CLASSES:
                piece_name = self.bridge_visual_name(box_slot, piece_type)
                if not piece_name:
                    continue

                piece_done = self.bridge_piece_done(box_slot, piece_type)

                if self.bridge_box_present(box_slot) and piece_done:
                    self.bridge_visual_fixed.pop((box_slot, piece_type), None)
                    self.live_bridge_visuals.pop(piece_name, None)
                    self.set_bridge_piece_pose_in_box(box_slot, piece_type)
                    continue

                self.bridge_visual_fixed.pop((box_slot, piece_type), None)
                self.live_bridge_visuals.pop(piece_name, None)
                self.set_visible(piece_name, False)

        if active_box_slot not in [1, 2, 3]:
            return

        for piece_type in BRIDGE_CLASSES:
            piece_info = self.bridge_memory(active_box_slot, piece_type)
            piece_done = self.bridge_piece_done(active_box_slot, piece_type)

            if not isinstance(piece_info, dict) or piece_done:
                continue

            self.set_bridge_piece_pose(active_box_slot, piece_type, piece_info)
            break

    def reset_slot(self, slot_id):
        self.hide_slot(slot_id)
        self.slots[slot_id] = self.new_slot_state()

    def show_only_lid_color(self, slot_id, lid_color):
        tracked_name = self.station_lid_visual_name(slot_id)
        local_names = set(LID_OBJECTS[slot_id].values())
        for color, name in LID_OBJECTS[slot_id].items():
            should_show = (
                name == tracked_name
                if tracked_name is not None
                else self.is_valid_color(lid_color) and color == lid_color
            )
            if should_show:
                self.set_visible(name, True)
            elif not self.lid_claimed_by_other_box(name, slot_id):
                self.set_visible(name, False)

        if tracked_name is not None and tracked_name not in local_names:
            self.set_visible(tracked_name, True)

    def show_only_box_color(self, slot_id, box_color):
        for color, name in BOX_OBJECTS[slot_id].items():
            self.set_visible(name, self.is_valid_color(box_color) and color == box_color)

    def show_cell(self, slot_id, battery_slot_id, color, polarity_ok, lock_color=False):
        if not self.is_valid_color(color):
            return

        cell = self.slots[slot_id]["cells"][battery_slot_id]
        if cell.get("color_locked", False):
            return
        cell["visible"] = True
        cell["color"] = color
        cell["polarity_ok"] = polarity_ok
        if lock_color:
            cell["color_locked"] = True

    def render_cell(self, slot_id, battery_slot_id):
        cell = self.slots[slot_id]["cells"][battery_slot_id]
        names = battery_object_names(slot_id, battery_slot_id)

        if not cell["visible"]:
            self.hide_one_battery(slot_id, battery_slot_id)
            return

        color = cell["color"]
        polarity_ok = cell["polarity_ok"]

        self.set_visible(names["base"], True)

        # Applied only during the one-time cell initialization for this box.
        self.set_pose_by_polarity(names["base"], polarity_ok)

        for color_key in self.VALID_COLORS:
            obj_name = names[color_key]
            should_show = color == color_key
            self.set_visible(obj_name, should_show)
            if should_show:
                self.set_pose_by_polarity(obj_name, polarity_ok)

    def render_cells(self, slot_id):
        for battery_slot_id in BATTERY_SLOT_IDS:
            self.render_cell(slot_id, battery_slot_id)

    def slot_number(self, slot_id):
        return RACK_TO_NUMBER.get(slot_id)

    def station_box_memory(self, slot_id):
        if self.station_logic is None:
            return None

        boxes = getattr(self.station_logic, "boxes", {}) or {}
        slot_num = self.slot_number(slot_id)
        return boxes.get(slot_num)

    def station_box_state(self, slot_id):
        box = self.station_box_memory(slot_id)
        if isinstance(box, dict):
            return box.get("state", None)
        return None

    def station_box_color(self, slot_id):
        box = self.station_box_memory(slot_id)
        if isinstance(box, dict):
            color = box.get("color", None)
            if self.is_valid_color(color):
                return color
        return None

    def station_lid_color(self, slot_id):
        box = self.station_box_memory(slot_id)
        if isinstance(box, dict):
            color = box.get("detected_lid_color", None)
            if self.is_valid_color(color):
                return color
        return None

    def station_lid_visual_name(self, slot_id):
        box = self.station_box_memory(slot_id)
        if isinstance(box, dict):
            lid_name = box.get("lid_visual_name")
            if lid_name:
                return str(lid_name)
        return None

    def station_slot_is_final(self, slot_id):
        return self.station_box_state(slot_id) in self.FINAL_MEMORY_STATES

    def lock_lid(self, slot_id, lid_color):
        if not self.is_valid_color(lid_color):
            return False

        slot = self.slots[slot_id]
        if slot["lid_locked"] and slot["lid_color"] != lid_color:
            return True

        slot["lid_color"] = lid_color
        slot["lid_locked"] = True
        slot["lid_owned_by_slot"] = True
        return True

    def lock_box(self, slot_id, box_color):
        if not self.is_valid_color(box_color):
            return False

        slot = self.slots[slot_id]
        if slot["box_locked"] and slot["box_color"] != box_color:
            return True

        previous_color = slot["box_color"]
        slot["box_color"] = box_color
        slot["box_locked"] = True

        lid_color = slot.get("lid_color")
        if previous_color != box_color and self.is_valid_color(lid_color) and lid_color != box_color:
            print(f"[RoboDK][BoxColor] {slot_id}: caja real {box_color}; la tapa inicial era {lid_color}")

        return True

    def render_slot(self, slot_id):
        slot = self.slots[slot_id]

        if slot["lid_locked"] and slot.get("lid_owned_by_slot", False):
            self.show_only_lid_color(slot_id, slot["lid_color"])
        elif not slot["lid_locked"]:
            self.hide_lids(slot_id)

        box_color = slot["box_color"] if self.is_valid_color(slot["box_color"]) else slot["lid_color"]
        self.show_only_box_color(slot_id, box_color)

        if slot["phase"] == "closed" and not slot.get("cells_released", False):
            self.hide_batteries(slot_id)

    def initialize_cells_once(self, slot_id):
        slot = self.slots[slot_id]
        if slot.get("cells_released", False):
            return True

        box = self.station_box_memory(slot_id)
        if not isinstance(box, dict) or not bool(box.get("initial_cells_captured", False)):
            return False

        cells = box.get("cells", []) or []
        if len(cells) < len(BATTERY_SLOT_IDS):
            return False

        for cell in cells[: len(BATTERY_SLOT_IDS)]:
            if not isinstance(cell, dict) or not self.is_valid_color(cell.get("color", None)):
                return False

        for idx, cell in enumerate(cells[: len(BATTERY_SLOT_IDS)]):
            color = cell.get("color", None)
            battery_slot_id = BATTERY_SLOT_IDS[idx]
            polarity_ok = cell.get("polarity_ok", None)
            self.show_cell(slot_id, battery_slot_id, color, polarity_ok, lock_color=True)

        self.render_cells(slot_id)
        slot["cells_released"] = True
        print(f"[RoboDK][Cells] {slot_id}: cuatro celdas fijadas al abrir; no se actualizaran de nuevo.")
        return True

    def should_reset_slot(self, slot_id, slot_state):
        if self.slots[slot_id].get("locked_final", False):
            return False

        if bool(slot_state.get("box_present", False)):
            return False

        phase = self.slots[slot_id]["phase"]
        if phase == "empty":
            return True

        return self.station_slot_is_final(slot_id)

    def mark_final_closed_if_needed(self, slot_id, slot_state):
        slot = self.slots[slot_id]
        lid_color = slot_state.get("lid_color", None)
        box_state = slot_state.get("box_state", "unknown")

        final_by_station = self.station_slot_is_final(slot_id)
        final_by_camera = slot["phase"] == "open" and box_state == "closed" and self.is_valid_color(lid_color)

        if not final_by_station and not final_by_camera:
            return False

        slot["phase"] = "final_closed"
        slot["locked_final"] = True

        if self.is_valid_color(lid_color):
            self.lock_lid(slot_id, lid_color)
        elif not slot["lid_locked"]:
            self.lock_lid(slot_id, self.station_lid_color(slot_id) or self.station_box_color(slot_id))

        if not slot["box_locked"]:
            self.lock_box(
                slot_id,
                self.station_box_color(slot_id)
                or slot_state.get("open_box_color", None)
                or lid_color
                or slot["box_color"],
            )

        self.render_slot(slot_id)
        return True

    def update_empty_slot(self, slot_id, slot_state):
        if not bool(slot_state.get("box_present", False)):
            self.hide_slot(slot_id)
            return

        lid_color = slot_state.get("lid_color", None)
        open_box_color = slot_state.get("open_box_color", None)

        if self.is_valid_color(lid_color):
            self.lock_lid(slot_id, lid_color)
            self.slots[slot_id]["phase"] = "closed"

            # Mientras la tapa tapa la caja, se muestra una caja provisional del mismo color.
            self.slots[slot_id]["box_color"] = lid_color
            self.slots[slot_id]["box_locked"] = False

            self.render_slot(slot_id)
            return

        if bool(slot_state.get("confirmed_open", False)) and self.is_valid_color(open_box_color):
            self.slots[slot_id]["phase"] = "open"
            self.lock_box(slot_id, open_box_color)
            self.render_slot(slot_id)
            self.initialize_cells_once(slot_id)
            return

        self.hide_slot(slot_id)

    def update_open_slot(self, slot_id, slot_state):
        slot = self.slots[slot_id]
        slot["phase"] = "open"

        if not slot["box_locked"]:
            self.lock_box(slot_id, slot_state.get("open_box_color", None) or self.station_box_color(slot_id))

        self.render_slot(slot_id)
        self.initialize_cells_once(slot_id)

    def update_slot(self, slot_id, slot_state):
        slot_state = slot_state or {}
        slot = self.slots[slot_id]

        if slot.get("locked_final", False):
            self.render_slot(slot_id)
            return

        if (
            slot["phase"] == "final_closed"
            and bool(slot_state.get("box_present", False))
            and not self.station_slot_is_final(slot_id)
        ):
            self.reset_slot(slot_id)

        if self.should_reset_slot(slot_id, slot_state):
            self.reset_slot(slot_id)
            return

        if self.slots[slot_id]["phase"] == "empty":
            self.update_empty_slot(slot_id, slot_state)
            return

        if self.mark_final_closed_if_needed(slot_id, slot_state):
            return

        box_state = slot_state.get("box_state", "unknown")
        open_box_color = slot_state.get("open_box_color", None)
        station_state = self.station_box_state(slot_id)
        camera_says_open = bool(slot_state.get("confirmed_open", False)) or box_state == "open"
        memory_says_open = station_state in self.OPEN_MEMORY_STATES

        if camera_says_open or memory_says_open or self.is_valid_color(open_box_color):
            self.update_open_slot(slot_id, slot_state)
            return

        # Si la camara pierde la caja durante el ciclo, mantenemos lo ultimo visible.
        self.render_slot(slot_id)

    def update_from_results(self, results):
        if self.visual_updates_locked:
            return

        results = results or {}
        self.current_bridge_state = results.get("bridge", {}) or {"pieces": []}
        for slot_id in RACK_SLOT_IDS:
            if self.robot_red_zone_active and slot_id == self.frozen_slot_id:
                self.render_slot(slot_id)
                continue
            self.update_slot(slot_id, results.get(slot_id, {}) or {})
        self.update_bridge_visuals()
