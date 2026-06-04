"""Shared robot speed profile helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app_config import (
    ROBOT_JOINT_ACCEL_MAX_DEG_S2,
    ROBOT_JOINT_SPEED_MAX_DEG_S,
    ROBOT_LINEAR_ACCEL_MAX_MM_S2,
    ROBOT_LINEAR_SPEED_MAX_MM_S,
    ROBOT_SPEED_PERCENT_MAX,
    ROBOT_SPEED_PERCENT_MIN,
)


@dataclass(frozen=True)
class RobotMotionSpeed:
    percent: float
    linear_speed_mm_s: float
    joint_speed_deg_s: float
    linear_accel_mm_s2: float
    joint_accel_deg_s2: float


def clamp_robot_speed_percent(
    speed_percent: float,
    min_percent: float = ROBOT_SPEED_PERCENT_MIN,
    max_percent: float = ROBOT_SPEED_PERCENT_MAX,
) -> float:
    return max(min_percent, min(max_percent, float(speed_percent)))


def build_robot_motion_speed(
    speed_percent: float,
    *,
    min_percent: float = ROBOT_SPEED_PERCENT_MIN,
    max_percent: float = ROBOT_SPEED_PERCENT_MAX,
    linear_speed_max_mm_s: float = ROBOT_LINEAR_SPEED_MAX_MM_S,
    joint_speed_max_deg_s: float = ROBOT_JOINT_SPEED_MAX_DEG_S,
    linear_accel_max_mm_s2: float = ROBOT_LINEAR_ACCEL_MAX_MM_S2,
    joint_accel_max_deg_s2: float = ROBOT_JOINT_ACCEL_MAX_DEG_S2,
) -> RobotMotionSpeed:
    percent = clamp_robot_speed_percent(speed_percent, min_percent, max_percent)
    scale = percent / 100.0
    return RobotMotionSpeed(
        percent=percent,
        linear_speed_mm_s=linear_speed_max_mm_s * scale,
        joint_speed_deg_s=joint_speed_max_deg_s * scale,
        linear_accel_mm_s2=linear_accel_max_mm_s2 * scale,
        joint_accel_deg_s2=joint_accel_max_deg_s2 * scale,
    )


def apply_robot_motion_speed(robot, speed: RobotMotionSpeed) -> None:
    """Apply the same motion limits for MoveJ and MoveL.

    RoboDK's Python API documents joint speed/acceleration in deg/s and
    deg/s2, so these values are intentionally not converted to radians.
    """
    robot.setSpeed(
        speed.linear_speed_mm_s,
        speed.joint_speed_deg_s,
        speed.linear_accel_mm_s2,
        speed.joint_accel_deg_s2,
    )

    # Keep explicit setters too: MoveJ can otherwise reuse RoboDK/driver
    # defaults, especially on the first Home movement.
    if hasattr(robot, "setSpeedJoints"):
        robot.setSpeedJoints(speed.joint_speed_deg_s)
    if hasattr(robot, "setAcceleration"):
        robot.setAcceleration(speed.linear_accel_mm_s2)
    if hasattr(robot, "setAccelerationJoints"):
        robot.setAccelerationJoints(speed.joint_accel_deg_s2)
