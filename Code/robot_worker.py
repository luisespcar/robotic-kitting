"""Background worker that serializes StationLogic and RoboDK actions.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import queue
import threading
import time
from copy import deepcopy

from app_config import *
from robot_commands import (
    COMMAND_UPDATE_RESULTS,
    RobotSpeedLimits,
    StationRobotExecutor,
    ack_safe_reconnect_command,
    pause_motion_command,
    resume_motion_command,
    set_speed_command,
    update_results_command,
)

class RobotLogicWorker:
    """Hilo secundario: manda results a StationLogic y actualiza RoboDK sin bloquear la cÃ¡mara."""

    def __init__(self, station_logic=None, robodk_updater=None, vision_settle_s=0.0):
        self.station_logic = station_logic
        self.robodk_updater = robodk_updater
        self._executor = StationRobotExecutor(
            RobotSpeedLimits(
                min_percent=ROBOT_SPEED_PERCENT_MIN,
                max_percent=ROBOT_SPEED_PERCENT_MAX,
                linear_speed_max_mm_s=ROBOT_LINEAR_SPEED_MAX_MM_S,
                joint_speed_max_deg_s=ROBOT_JOINT_SPEED_MAX_DEG_S,
                linear_accel_max_mm_s2=ROBOT_LINEAR_ACCEL_MAX_MM_S2,
                joint_accel_max_deg_s2=ROBOT_JOINT_ACCEL_MAX_DEG_S2,
            )
        )
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._stop_event = threading.Event()
        self._command_queue = queue.Queue()
        self._latest_payload = None
        self._busy = False
        self._processed_count = 0
        self._submitted_count = 0
        self._last_error = None
        self._vision_settle_s = float(vision_settle_s)
        self._ignore_vision_until = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, station_results=None, robodk_results=None, robot_red_zone_active=None):
        if station_results is None and robodk_results is None:
            return
        with self._lock:
            self._latest_payload = update_results_command(
                station_results=station_results,
                robodk_results=robodk_results,
                robot_red_zone_active=robot_red_zone_active,
            )
            self._submitted_count += 1
        self._event.set()

    def request_set_speed(self, speed_percent, wait=False, timeout=2.0):
        command = set_speed_command(speed_percent, wait=wait)
        self._enqueue_command(command)
        return self._await_command(command, timeout, default=float(speed_percent))

    def request_pause_motion(self, wait=False, timeout=2.0):
        command = pause_motion_command(wait=wait)
        self._enqueue_command(command)
        return self._await_command(command, timeout, default=True)

    def request_resume_motion(self, wait=False, timeout=2.0):
        command = resume_motion_command(wait=wait)
        self._enqueue_command(command)
        return self._await_command(command, timeout, default=True)

    def request_acknowledge_safe_reconnect(self, move_home_after_reconnect=False, wait=False, timeout=5.0):
        command = ack_safe_reconnect_command(
            move_home_after_reconnect=move_home_after_reconnect,
            wait=wait,
        )
        self._enqueue_command(command)
        return self._await_command(command, timeout, default=True)

    def is_busy(self):
        with self._lock:
            return self._busy

    def status_text(self):
        with self._lock:
            now = time.time()
            if self._busy:
                return "ROBOT: BUSY"
            if now < self._ignore_vision_until:
                return f"ROBOT: SETTLING {self._ignore_vision_until - now:.1f}s"
            if self._latest_payload is not None:
                return "ROBOT: PENDING"
            return "ROBOT: READY"

    def stop(self, timeout=2.0):
        self._stop_event.set()
        self._event.set()
        self._thread.join(timeout=timeout)

    def _enqueue_command(self, command):
        self._command_queue.put(command)
        with self._lock:
            self._submitted_count += 1
        self._event.set()

    @staticmethod
    def _await_command(command, timeout, default):
        if command.done_event is None:
            return default
        if not command.done_event.wait(timeout=timeout):
            print(f"[RobotLogicWorker][AVISO] Timeout esperando comando {command.kind}.")
            return default
        if command.error is not None:
            print(f"[RobotLogicWorker][ERROR] {command.kind}: {command.error}")
            return default
        return command.result

    def _push_robodk_update(self, results, robot_red_zone_active=None):
        if self.robodk_updater is None or results is None:
            return

        if robot_red_zone_active is not None and hasattr(self.robodk_updater, "set_robot_red_zone"):
            self.robodk_updater.set_robot_red_zone(bool(robot_red_zone_active))

        live_results = results
        if self.station_logic is not None and hasattr(self.station_logic, "freeze_results_for_live_update"):
            live_results = self.station_logic.freeze_results_for_live_update(results)

        self.robodk_updater.update_from_results(live_results)

    def _pop_latest_payload(self):
        with self._lock:
            payload = self._latest_payload
            self._latest_payload = None
        return payload

    def _set_idle(self):
        with self._lock:
            was_busy = self._busy
            self._busy = False
            if was_busy and self._vision_settle_s > 0:
                self._ignore_vision_until = max(self._ignore_vision_until, time.time() + self._vision_settle_s)

    def _set_busy(self):
        with self._lock:
            self._busy = True

    def _execute_command(self, command):
        if command.kind == COMMAND_UPDATE_RESULTS:
            station_results = command.payload.get("station_results")
            robodk_results = command.payload.get("robodk_results")
            robot_red_zone_active = command.payload.get("robot_red_zone_active")

            if self.robodk_updater is not None and robodk_results is not None:
                self._push_robodk_update(robodk_results, robot_red_zone_active)

            if self.station_logic is not None and station_results is not None:
                self.station_logic.update(station_results)

            return None

        return self._executor.execute(self.station_logic, command)

    def _consume_next_command(self):
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None

    def _loop(self):
        while not self._stop_event.is_set():
            self._event.wait(timeout=0.1)
            self._event.clear()

            while not self._stop_event.is_set():
                command = self._consume_next_command()
                if command is None:
                    command = self._pop_latest_payload()

                if command is None:
                    self._set_idle()
                    break

                self._set_busy()
                try:
                    result = self._execute_command(command)
                    command.resolve(result)

                    with self._lock:
                        self._processed_count += 1
                        self._last_error = None

                except Exception as exc:
                    command.reject(exc)
                    with self._lock:
                        self._last_error = str(exc)
                    print(f"[RobotLogicWorker][ERROR] {exc}")
                    if self.station_logic is not None and hasattr(self.station_logic, "enter_robot_safety_stop"):
                        self.station_logic.enter_robot_safety_stop("RobotLogicWorker", exc)

                finally:
                    self._set_idle()

                with self._lock:
                    has_more = self._latest_payload is not None
                if not has_more:
                    has_more = not self._command_queue.empty()
                if not has_more:
                    break
