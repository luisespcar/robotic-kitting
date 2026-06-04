"""StationLogic assembled from focused mixins.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *
from station_mixins import (
    BridgeMixin,
    CellMotionMixin,
    CellProcessingMixin,
    CompletionMixin,
    EvaluationMixin,
    LidFlowMixin,
    MemoryMixin,
    RoboDKMotionMixin,
    SafetyMixin,
)


class StationLogic(
    MemoryMixin,
    SafetyMixin,
    RoboDKMotionMixin,
    LidFlowMixin,
    CellMotionMixin,
    BridgeMixin,
    CellProcessingMixin,
    CompletionMixin,
    EvaluationMixin,
):
    ROBOT_IP = "192.168.0.101"
    DASHBOARD_PORT = 29999
    ROBODK_PORT = 30002

    def __init__(
        self,
        rdk: Optional[Robolink] = None,
        robot_name: str = "UR10e",
        simulate: bool = True,
        move_home_on_start: bool = False,
        dry_run: bool = False,
        memory_file_path: Optional[str] = None,  # compatibilidad: no se usa
        check_robodk_items_on_start: bool = True,
        fail_if_missing_robodk_items: bool = False,
        robodk_updater: Optional[Any] = None,
        action_cooldown_s: float = 0.5,
    ):
        self.simulate = bool(simulate)
        self.dry_run = bool(dry_run)
        self.robodk_updater = robodk_updater
        self.action_cooldown_s = float(action_cooldown_s)
        self.last_action_time = 0.0

        self.RDK = rdk if rdk is not None else Robolink()
        self.RDK.setRunMode(RUNMODE_SIMULATE if self.simulate else RUNMODE_RUN_ROBOT)
        print("[StationLogic] Modo SIMULACIÓN" if self.simulate else "[StationLogic] Modo ROBOT REAL")

        self.robot = self.RDK.Item(robot_name)
        if not self.robot.Valid():
            raise RuntimeError(f"Robot {robot_name!r} no encontrado en RoboDK")

        self.reset_runtime_memory()
        self.last_state_signature: Optional[Tuple[Any, ...]] = None
        self.last_camera_results: Dict[str, Any] = {}
        self.last_camera_summary: Dict[str, Any] = {}
        self.open_box_confirmation_slot: Optional[int] = None
        self.open_box_confirmation_signature: Optional[Tuple[Any, ...]] = None
        self.open_box_confirmation_since = 0.0
        self.cell_treatment_locked = False
        self.frozen_active_slot_id: Optional[str] = None
        self.frozen_active_slot_results: Optional[Dict[str, Any]] = None

        self.robot_safety_stop_active = False
        self.robot_requires_human_ack = False
        self.robot_last_error: Optional[str] = None
        self.robot_last_error_context: Optional[str] = None
        self.shutdown_requested = False
        self.runtime_pause_active = False
        # Última pieza física que ha sido pickeada por el robot (p.e. 'S05')
        self.last_picked_object_id: Optional[str] = None

        if check_robodk_items_on_start:
            missing = self.check_required_robodk_items()
            if missing and fail_if_missing_robodk_items:
                raise RuntimeError("Faltan elementos obligatorios en RoboDK: " + ", ".join(missing))

        if move_home_on_start:
            self.move_home()
