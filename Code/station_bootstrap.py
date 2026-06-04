"""Asynchronous RoboDK/StationLogic bootstrap worker.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import threading

from app_config import *
from robodk_live_updater import RoboDKLiveUpdater
from station_logic import StationLogic

class StationBootstrapWorker:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._done = False
        self._status = "IDLE"
        self._error = None
        self._payload = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _set_status(self, status):
        with self._lock:
            self._status = str(status)

    def _run(self):
        robodk_updater = None
        station_logic = None
        try:
            if ENABLE_ROBODK_LIVE_UPDATE:
                self._set_status("Conectando RoboDK live updater...")
                robodk_updater = RoboDKLiveUpdater()

            if ENABLE_STATION_LOGIC:
                self._set_status("Inicializando StationLogic...")
                station_logic = StationLogic(
                    rdk=robodk_updater.rdk if robodk_updater is not None else None,
                    robot_name="UR10e",
                    simulate=STATION_SIMULATION_MODE,
                    move_home_on_start=False,
                    dry_run=STATION_DRY_RUN,
                    robodk_updater=robodk_updater,
                )

                if robodk_updater is not None:
                    robodk_updater.bind_station_logic(station_logic)

                if RUN_REPLACE_ALL_ON_START:
                    self._set_status(f"Ejecutando {REPLACE_ALL_PROGRAM_NAME}...")
                    replace_all_ok = station_logic.run_program_in_simulation(REPLACE_ALL_PROGRAM_NAME)
                    if not replace_all_ok:
                        print(f"[RoboDK][AVISO] No se pudo ejecutar {REPLACE_ALL_PROGRAM_NAME}")
                    elif robodk_updater is not None:
                        self._set_status("Refrescando cache RoboDK...")
                        robodk_updater.refresh_all_items()

                if not STATION_SIMULATION_MODE and not STATION_DRY_RUN:
                    self._set_status("Conectando robot real...")
                    station_logic.connect_robot()

            with self._lock:
                self._payload = {
                    "robodk_updater": robodk_updater,
                    "station_logic": station_logic,
                }
                self._done = True
                self._status = "READY"
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
                self._done = True
                self._status = "ERROR"

    def poll(self):
        with self._lock:
            payload = self._payload
            self._payload = None
            return {
                "done": self._done,
                "status": self._status,
                "error": self._error,
                "payload": payload,
            }
