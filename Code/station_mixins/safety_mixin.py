"""StationLogic SafetyMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from station_config import *
from station_helpers import *


class SafetyMixin:
    def safety_status_text(self) -> str:
        if self.robot_safety_stop_active:
            context = self.robot_last_error_context or "robot"
            return f"ROBOT: PARADA SEGURA ({context}) - revisar y pulsar r"
        return "ROBOT: OK"
    def enter_robot_safety_stop(self, context: str, exc: Optional[BaseException] = None) -> None:
        self.robot_safety_stop_active = True
        self.robot_requires_human_ack = True
        self.robot_last_error_context = context
        self.robot_last_error = str(exc) if exc is not None else context

        print("\n[SEGURIDAD][ROBOT] Movimiento/comando detenido.")
        print("[SEGURIDAD][ROBOT] Revisa físicamente la celda, libera protective stop si existe")
        print("[SEGURIDAD][ROBOT] y pulsa 'r' cuando sea seguro reconectar.")
        if self.robot_last_error:
            print(f"[SEGURIDAD][DETALLE] {self.robot_last_error}")
    def assert_robot_ready(self, context: str) -> bool:
        if self.robot_safety_stop_active:
            print(f"[SEGURIDAD] Acción bloqueada ({context}). Esperando tecla 'r'.")
            return False
        if self.runtime_pause_active:
            print(f"[StationLogic] Acción retenida por pausa temporal ({context}).")
            return False
        return True
    def stop_cycle_if_needed(self, context: str = "") -> bool:
        if self.robot_safety_stop_active:
            print(f"[SEGURIDAD] Ciclo abortado ({context}). Esperando tecla 'r'.")
            return True
        if self.runtime_pause_active:
            print(f"[StationLogic] Ciclo retenido por pausa temporal ({context}).")
            return True
        return False
    def acknowledge_robot_safe_and_reconnect(self, move_home_after_reconnect: bool = False) -> bool:
        if not self.robot_safety_stop_active and not self.robot_requires_human_ack:
            print("[SEGURIDAD] No hay parada segura pendiente.")
            return True

        print("[SEGURIDAD] Confirmación humana recibida.")

        ok = True if self.simulate or self.dry_run else self.connect_robot()
        if not ok:
            print("[SEGURIDAD][ERROR] No se pudo reconectar. Mantengo bloqueo seguro.")
            return False

        self.robot_safety_stop_active = False
        self.robot_requires_human_ack = False
        self.robot_last_error = None
        self.robot_last_error_context = None
        self.last_state_signature = None
        print("[SEGURIDAD] Lógica desbloqueada.")

        if move_home_after_reconnect:
            self.move_home()
        return True
