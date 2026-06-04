"""StationLogic BridgeMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from math import degrees

from station_config import *
from station_helpers import *


class BridgeMixin:
    def bridge_complete(self, box_slot: int) -> bool:
        bridge_parts_done = self.boxes[box_slot].get("bridge_parts_done", {}) or {}
        return all(bool(bridge_parts_done.get(piece_type, False)) for piece_type in BRIDGE_REQUIRED_TYPES)
    def bridge_piece_from_results(self, results: Dict[str, Any], piece_type: str) -> Optional[Dict[str, Any]]:
        bridge_state = (results.get("bridge", {}) or {})
        piece = bridge_state.get(piece_type)
        if isinstance(piece, dict):
            return deepcopy(piece)
        return None
    def cache_bridge_piece_positions(self, box_slot: int, results: Dict[str, Any]) -> bool:
        box = self.boxes[box_slot]
        bridge_parts_info = box.setdefault("bridge_parts_info", {})

        for piece_type in BRIDGE_REQUIRED_TYPES:
            piece_info = self.bridge_piece_from_results(results, piece_type)
            if piece_info is None:
                print(f"[Bridge] Box{box_slot}: no detecto pieza {piece_type} para memorizar.")
                return False

            # Guardamos la pieza tal cual llega de vision, pero el movimiento
            # SOLO usara center_x_rdk_mm/center_y_rdk_mm.
            cached_info = deepcopy(piece_info)
            cached_info["memorized_at"] = now_iso()
            bridge_parts_info[piece_type] = cached_info

        print(
            f"[Bridge] Box{box_slot}: posiciones small/large memorizadas "
            f"antes del pick."
        )
        return True
    @staticmethod
    def _bridge_first_number(data: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None
    def bridge_target_pose_from_piece(self, piece_info: Dict[str, Any], *, approach: bool) -> Any:
        source_name = BRIDGE_SOURCE_UP_TARGET if approach else BRIDGE_SOURCE_DOWN_TARGET
        xyzrxyz = self.target_xyzrxyz(source_name)
        x_mm = float(piece_info["center_x_rdk_mm"])
        y_mm = float(piece_info["center_y_rdk_mm"])
        angle_deg = float(piece_info.get("rotation_deg", 0.0)) * BRIDGE_ROTATION_SIGN + BRIDGE_ROTATION_OFFSET_DEG
        xyzrxyz[0] += x_mm
        xyzrxyz[1] += y_mm
        pose = TxyzRxyz_2_Pose(xyzrxyz)
        return pose * rotz(radians(angle_deg))
    def bridge_pick_pose(self, piece_type: str, piece_info: Dict[str, Any], *, approach: bool) -> Any:
        return self.bridge_target_pose_from_piece(piece_info, approach=approach)
    def log_bridge_pose_for_robodk(self, label: str, pose) -> bool:
        xyzrxyz = list(Pose_2_TxyzRxyz(pose))
        print(
            f"[BridgeMove] {label} -> "
            f"X={float(pose[0, 3]):.2f} Y={float(pose[1, 3]):.2f} Z={float(pose[2, 3]):.2f} "
            f"Rz={degrees(float(xyzrxyz[5])):.2f}deg"
        )
        return True
    def create_or_update_bridge_pick_target(self, name: str, piece_info: Dict[str, Any], *, approach: bool):
        bridge_frame = self.get_frame(BRIDGE_FRAME_NAME)
        source_name = BRIDGE_SOURCE_UP_TARGET if approach else BRIDGE_SOURCE_DOWN_TARGET
        source_target = self.get_target(source_name)
        target = self.RDK.Item(name, ITEM_TYPE_TARGET)
        if not target.Valid():
            target = self.RDK.AddTarget(name, bridge_frame)
        if hasattr(target, "setAsCartesianTarget"):
            try:
                target.setAsCartesianTarget()
            except Exception:
                pass

        target_pose = self.bridge_target_pose_from_piece(piece_info, approach=approach)
        expected_x, expected_y = float(target_pose[0, 3]), float(target_pose[1, 3])
        source_pose = source_target.Pose()

        target.setParent(bridge_frame)
        target.setPose(target_pose)
        saved_pose = target.Pose()
        saved_x, saved_y = float(saved_pose[0, 3]), float(saved_pose[1, 3])

        if abs(saved_x - expected_x) > 1e-6 or abs(saved_y - expected_y) > 1e-6:
            corrected_xyzrxyz = list(Pose_2_TxyzRxyz(saved_pose))
            corrected_xyzrxyz[0] = expected_x
            corrected_xyzrxyz[1] = expected_y
            target.setPose(TxyzRxyz_2_Pose(corrected_xyzrxyz))
            saved_pose = target.Pose()
            saved_x, saved_y = float(saved_pose[0, 3]), float(saved_pose[1, 3])

        try:
            target.setVisible(False)
        except Exception:
            pass
        return target
    def prepare_bridge_pick_targets_and_visuals(self, box_slot: int) -> bool:
        box = self.boxes[box_slot]
        bridge_parts_info = box.get("bridge_parts_info", {}) or {}

        for piece_type in BRIDGE_REQUIRED_TYPES:
            if box.get("bridge_parts_done", {}).get(piece_type, False):
                continue

            piece_info = bridge_parts_info.get(piece_type)
            if not isinstance(piece_info, dict):
                print(f"[Bridge] Box{box_slot}: no hay memoria para fijar visual {piece_type}.")
                return False

            self.create_or_update_bridge_pick_target(
                BRIDGE_APPROACH_TARGET_BY_TYPE[piece_type],
                piece_info,
                approach=True,
            )
            self.create_or_update_bridge_pick_target(
                BRIDGE_PICK_TARGET_BY_TYPE[piece_type],
                piece_info,
                approach=False,
            )

        robodk_updater = getattr(self, "robodk_updater", None)
        if robodk_updater is None:
            return True
        if not hasattr(robodk_updater, "show_bridge_pick_visuals_from_targets"):
            return True

        return bool(robodk_updater.show_bridge_pick_visuals_from_targets(box_slot))
    def pick_bridge_piece(self, piece_type: str, piece_info: Dict[str, Any]) -> bool:
        approach_target = self.create_or_update_bridge_pick_target(
            BRIDGE_APPROACH_TARGET_BY_TYPE[piece_type],
            piece_info,
            approach=True,
        )
        pick_target = self.create_or_update_bridge_pick_target(
            BRIDGE_PICK_TARGET_BY_TYPE[piece_type],
            piece_info,
            approach=False,
        )
        approach_pose = approach_target.Pose()
        pick_pose = pick_target.Pose()

        return self.sequence(
            f"[Bridge] Pick {piece_type} raw=({piece_info.get('center_x_mm_raw', 0.0):.1f}, "
            f"{piece_info.get('center_y_mm_raw', 0.0):.1f}) "
            f"R={piece_info.get('rotation_deg', 0.0):.1f} "
            f"approach_pose=({float(approach_pose[0, 3]):.1f}, {float(approach_pose[1, 3]):.1f}, {float(approach_pose[2, 3]):.1f}) "
            f"pick_pose=({float(pick_pose[0, 3]):.1f}, {float(pick_pose[1, 3]):.1f}, {float(pick_pose[2, 3]):.1f})",
            lambda: self.movej_target(BRIDGE_PREPARE_TARGET),
            self.gripperopen,
            self.set_bridge_frame,
            lambda: self.log_bridge_pose_for_robodk(f"{piece_type}:approach", approach_target.Pose()),
            lambda: self.robot_call(
                f"MoveL:{approach_target.Name()}",
                lambda: self.robot.MoveL(approach_target),
            ),
            lambda: self.log_bridge_pose_for_robodk(f"{piece_type}:pick", pick_target.Pose()),
            lambda: self.robot_call(
                f"MoveL:{pick_target.Name()}",
                lambda: self.robot.MoveL(pick_target),
            ),
            self.gripperclosebridge,
            lambda: self.log_bridge_pose_for_robodk(f"{piece_type}:retreat", approach_target.Pose()),
            lambda: self.robot_call(
                f"MoveL:{approach_target.Name()}",
                lambda: self.robot.MoveL(approach_target),
            ),
            lambda: self.movej_target(BRIDGE_PREPARE_TARGET),
        )
    def place_bridge_piece_in_box(self, box_slot: int, piece_type: str) -> bool:
        target_name = BRIDGE_TARGET_BY_TYPE[piece_type]
        target_down_name = BRIDGE_TARGET_DOWN_BY_TYPE[piece_type]
        return self.sequence(
            f"[Bridge] Place {piece_type} en Box{box_slot}",
            lambda: self.set_box_frame(box_slot),
            lambda: self.movej_target(target_name),
            lambda: self.movel_target(target_down_name),
            self.bridgeopen,
            lambda: self.movel_target(target_name),
            lambda: self.movej_target(BRIDGE_PREPARE_TARGET),
        )
    def process_bridge_piece_for_box(self, box_slot: int, piece_type: str, results: Dict[str, Any]) -> bool:
        box = self.boxes[box_slot]
        bridge_parts_done = box.setdefault("bridge_parts_done", {piece: False for piece in BRIDGE_REQUIRED_TYPES})
        if bridge_parts_done.get(piece_type, False):
            return True

        piece_info = deepcopy((box.get("bridge_parts_info", {}) or {}).get(piece_type))
        if not isinstance(piece_info, dict):
            piece_info = self.bridge_piece_from_results(results, piece_type)
        if piece_info is None:
            print(f"[Bridge] Box{box_slot}: no detecto pieza {piece_type}. Esperando vision.")
            return False

        ok = self.sequence(
            f"[Bridge] Box{box_slot}: procesando pieza {piece_type}",
            lambda: self.pick_bridge_piece(piece_type, piece_info),
            lambda: self.place_bridge_piece_in_box(box_slot, piece_type),
        )
        if not ok:
            return False

        bridge_parts_done[piece_type] = True
        box.setdefault("bridge_parts_info", {})[piece_type] = piece_info
        box["bridge_parts_info"][piece_type]["placed_at"] = now_iso()
        print(
            f"[Bridge] Box{box_slot}: {piece_type} colocada "
            f"(raw=({piece_info.get('center_x_mm_raw', 0.0):.1f}, {piece_info.get('center_y_mm_raw', 0.0):.1f}), "
            f"rdk=({piece_info.get('center_x_rdk_mm', 0.0):.1f}, "
            f"{piece_info.get('center_y_rdk_mm', 0.0):.1f}), "
            f"R={piece_info.get('rotation_deg'):.1f})"
        )
        return True
    def buscar_bridge(self, box_slot: int, results: Optional[Dict[str, Any]] = None) -> bool:
        box = self.boxes[box_slot]
        box["state"] = "bridges_pending"
        box.setdefault("bridge_parts_done", {piece: False for piece in BRIDGE_REQUIRED_TYPES})
        box.setdefault("bridge_parts_info", {})
        box.setdefault("bridge_visual_preview_done", False)
        box.setdefault("bridge_started_at", now_iso())

        if not isinstance(results, dict):
            print(f"[Bridge] Box{box_slot}: sin resultados de vision bridge.")
            return False

        if not self.should_scan_bridge_vision() or self.bridge_scan_box_slot != box_slot:
            print(f"[Bridge] Box{box_slot}: moviendo a {BRIDGE_SCAN_TARGET} para escanear small/large.")
            if not self.movej_target(BRIDGE_SCAN_TARGET):
                return False
            self.activate_bridge_scan(box_slot)
            return False

        bridge_state = (results.get("bridge", {}) or {})
        if not any(isinstance(bridge_state.get(piece_type), dict) for piece_type in BRIDGE_REQUIRED_TYPES):
            print(f"[Bridge] Box{box_slot}: esperando deteccion bridge en Home.")
            return False

        if not self.movej_target(BRIDGE_PREPARE_TARGET):
            return False

        if not self.cache_bridge_piece_positions(box_slot, results):
            return False

        if not box.get("bridge_visual_preview_done", False):
            if not self.prepare_bridge_pick_targets_and_visuals(box_slot):
                return False
            box["bridge_visual_preview_done"] = True
            print(f"[Bridge] Box{box_slot}: small/large visibles y fijas desde targets de pick.")

        for piece_type in BRIDGE_REQUIRED_TYPES:
            if not self.process_bridge_piece_for_box(box_slot, piece_type, results):
                return False

        self.deactivate_bridge_scan()
        box["state"] = "bridge_ready"
        box["bridge_visual_preview_done"] = False
        box["bridge_checked_at"] = now_iso()
        box["bridge_finished_at"] = now_iso()
        print(f"[Bridge] Box{box_slot}: small y large colocadas. Caja lista para tapa.")
        return True
    def find_pending_bridge_box(self) -> Optional[int]:
        for box_slot in [1, 2, 3]:
            box = self.boxes[box_slot]
            if not box.get("present"):
                continue

            if box.get("state") == "bridges_pending":
                return box_slot

            if (
                box.get("state") in {"cells_complete", "cells_complete_waiting_lid"}
                and self.box_complete(box_slot)
                and not self.bridge_complete(box_slot)
            ):
                print(
                    f"[Bridge] Box{box_slot}: celdas completas; "
                    "priorizo bridges antes de retirar otra tapa."
                )
                return box_slot
        return None
