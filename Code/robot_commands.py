"""Thread-safe robot worker commands and speed execution helpers.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from robot_speed_profile import apply_robot_motion_speed, build_robot_motion_speed

COMMAND_UPDATE_RESULTS = "update_results"
COMMAND_SET_SPEED = "set_speed"
COMMAND_PAUSE_MOTION = "pause_motion"
COMMAND_RESUME_MOTION = "resume_motion"
COMMAND_ACK_SAFE_RECONNECT = "ack_safe_reconnect"


@dataclass
class RobotWorkerCommand:
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    done_event: Optional[threading.Event] = None
    result: Any = None
    error: Optional[BaseException] = None

    def resolve(self, result: Any = None) -> None:
        self.result = result
        if self.done_event is not None:
            self.done_event.set()

    def reject(self, error: BaseException) -> None:
        self.error = error
        if self.done_event is not None:
            self.done_event.set()


def _make_command(kind: str, wait: bool = False, **payload: Any) -> RobotWorkerCommand:
    return RobotWorkerCommand(
        kind=kind,
        payload=payload,
        done_event=threading.Event() if wait else None,
    )


def update_results_command(
    station_results: Optional[Dict[str, Any]] = None,
    robodk_results: Optional[Dict[str, Any]] = None,
    robot_red_zone_active: Optional[bool] = None,
) -> RobotWorkerCommand:
    return _make_command(
        COMMAND_UPDATE_RESULTS,
        station_results=None if station_results is None else dict(station_results),
        robodk_results=None if robodk_results is None else dict(robodk_results),
        robot_red_zone_active=None if robot_red_zone_active is None else bool(robot_red_zone_active),
    )


def set_speed_command(speed_percent: float, wait: bool = False) -> RobotWorkerCommand:
    return _make_command(COMMAND_SET_SPEED, wait=wait, speed_percent=float(speed_percent))


def pause_motion_command(wait: bool = False) -> RobotWorkerCommand:
    return _make_command(COMMAND_PAUSE_MOTION, wait=wait)


def resume_motion_command(wait: bool = False) -> RobotWorkerCommand:
    return _make_command(COMMAND_RESUME_MOTION, wait=wait)


def ack_safe_reconnect_command(
    move_home_after_reconnect: bool = False,
    wait: bool = False,
) -> RobotWorkerCommand:
    return _make_command(
        COMMAND_ACK_SAFE_RECONNECT,
        wait=wait,
        move_home_after_reconnect=bool(move_home_after_reconnect),
    )


@dataclass(frozen=True)
class RobotSpeedLimits:
    min_percent: float
    max_percent: float
    linear_speed_max_mm_s: float
    joint_speed_max_deg_s: float
    linear_accel_max_mm_s2: float
    joint_accel_max_deg_s2: float


class StationRobotExecutor:
    def __init__(self, speed_limits: RobotSpeedLimits):
        self.speed_limits = speed_limits

    def clamp_speed_percent(self, speed_percent: float) -> float:
        return max(
            self.speed_limits.min_percent,
            min(self.speed_limits.max_percent, float(speed_percent)),
        )

    def execute(self, station_logic: Any, command: RobotWorkerCommand) -> Any:
        if command.kind == COMMAND_SET_SPEED:
            return self._set_speed(station_logic, command.payload.get("speed_percent", 100.0))
        if command.kind == COMMAND_PAUSE_MOTION:
            return self._pause_motion(station_logic)
        if command.kind == COMMAND_RESUME_MOTION:
            return self._resume_motion(station_logic)
        if command.kind == COMMAND_ACK_SAFE_RECONNECT:
            return self._ack_safe_reconnect(
                station_logic,
                bool(command.payload.get("move_home_after_reconnect", False)),
            )
        raise ValueError(f"Comando de robot no soportado: {command.kind}")

    def _set_speed(self, station_logic: Any, speed_percent: float) -> float:
        speed_percent = self.clamp_speed_percent(speed_percent)

        if station_logic is None:
            print(f"[RobotSpeed][AVISO] StationLogic no inicializado. Velocidad solicitada: {speed_percent:.0f}%")
            return speed_percent

        robot = getattr(station_logic, "robot", None)
        if robot is None or not robot.Valid():
            print(f"[RobotSpeed][AVISO] Robot no valido. Velocidad solicitada: {speed_percent:.0f}%")
            return speed_percent

        speed = build_robot_motion_speed(
            speed_percent,
            min_percent=self.speed_limits.min_percent,
            max_percent=self.speed_limits.max_percent,
            linear_speed_max_mm_s=self.speed_limits.linear_speed_max_mm_s,
            joint_speed_max_deg_s=self.speed_limits.joint_speed_max_deg_s,
            linear_accel_max_mm_s2=self.speed_limits.linear_accel_max_mm_s2,
            joint_accel_max_deg_s2=self.speed_limits.joint_accel_max_deg_s2,
        )

        apply_robot_motion_speed(robot, speed)
        station_logic.robot_speed_percent = speed.percent
        print(
            f"[RobotSpeed] Velocidad robot = {speed.percent:.0f}% "
            f"({speed.linear_speed_mm_s:.1f} mm/s, {speed.joint_speed_deg_s:.1f} deg/s)"
        )
        return speed.percent

    @staticmethod
    def _pause_motion(station_logic: Any) -> bool:
        if station_logic is None:
            return False
        if hasattr(station_logic, "pause_robot_motion"):
            return bool(station_logic.pause_robot_motion())
        return False

    @staticmethod
    def _resume_motion(station_logic: Any) -> bool:
        if station_logic is None:
            return False
        if hasattr(station_logic, "resume_robot_motion"):
            return bool(station_logic.resume_robot_motion())
        return False

    @staticmethod
    def _ack_safe_reconnect(station_logic: Any, move_home_after_reconnect: bool) -> bool:
        if station_logic is None:
            return False
        if hasattr(station_logic, "acknowledge_robot_safe_and_reconnect"):
            return bool(
                station_logic.acknowledge_robot_safe_and_reconnect(
                    move_home_after_reconnect=move_home_after_reconnect
                )
            )
        return False
