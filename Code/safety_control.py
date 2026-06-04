"""Robot speed helpers and hand-presence state recording.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from app_config import *
from robot_speed_profile import (
    apply_robot_motion_speed,
    build_robot_motion_speed,
    clamp_robot_speed_percent,
)


def set_station_robot_speed(station_logic, speed_percent, robot_worker=None):
    speed_percent = clamp_robot_speed_percent(speed_percent)

    if robot_worker is not None:
        robot_worker.request_set_speed(speed_percent, wait=False)
        print(f"[RobotSpeed] Cambio de velocidad solicitado = {speed_percent:.0f}%")
        return speed_percent

    if station_logic is None:
        print(f"[RobotSpeed][AVISO] StationLogic no inicializado. Velocidad solicitada: {speed_percent:.0f}%")
        return speed_percent

    robot = getattr(station_logic, "robot", None)
    if robot is None or not robot.Valid():
        print(f"[RobotSpeed][AVISO] Robot no vÃ¡lido. Velocidad solicitada: {speed_percent:.0f}%")
        return speed_percent

    speed = build_robot_motion_speed(speed_percent)

    try:
        apply_robot_motion_speed(robot, speed)
        station_logic.robot_speed_percent = speed.percent
        print(
            f"[RobotSpeed] Velocidad robot = {speed.percent:.0f}% "
            f"({speed.linear_speed_mm_s:.1f} mm/s, {speed.joint_speed_deg_s:.1f} deg/s)"
        )
        return speed.percent
    except Exception as exc:
        print(f"[RobotSpeed][ERROR] No se pudo cambiar velocidad: {exc}")
        current_speed = getattr(station_logic, "robot_speed_percent", speed_percent)
        return clamp_robot_speed_percent(current_speed)


class HandSafetyController:
    def __init__(self, station_logic, initial_speed_percent, robot_worker=None):
        self.station_logic = station_logic
        self.robot_worker = robot_worker
        self.normal_speed_percent = clamp_robot_speed_percent(initial_speed_percent)
        self.applied_speed_percent = None

    def set_normal_speed(self, speed_percent):
        self.normal_speed_percent = clamp_robot_speed_percent(speed_percent)

    def current_speed_text(self):
        if self.applied_speed_percent is None:
            return f"{self.normal_speed_percent:.0f}%"
        return f"{self.applied_speed_percent:.0f}%"

    def apply(self, hand_state):
        # Presence is data for station logic; it never commands robot motion.
        try:
            if self.station_logic is not None:
                self.station_logic.last_hand_state = dict(hand_state or {})
        except Exception:
            pass

        self.applied_speed_percent = self.normal_speed_percent
        return self.applied_speed_percent
