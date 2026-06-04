"""StationLogic RoboDKMotionMixin methods.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from app_config import (
    ROBOT_SPEED_PERCENT_DEFAULT,
)
from robot_speed_profile import apply_robot_motion_speed, build_robot_motion_speed
from station_config import *
from station_helpers import *


class RoboDKMotionMixin:
    def connect_robot(self) -> bool:
        if self.simulate:
            print("[RobotConnect] SIMULACIÓN: no conecto al UR real")
            return True
        if self.dry_run:
            print("[RobotConnect][DRY_RUN] No se conecta al robot")
            return True

        for attempt in range(1, ROBOT_CONNECT_RETRIES + 1):
            try:
                try:
                    self.robot.Disconnect()
                except Exception:
                    pass

                time.sleep(ROBOT_CONNECT_RETRY_DELAY_S)
                self.robot.setConnectionParams(self.ROBOT_IP, self.ROBODK_PORT, "", "", "")
                if bool(self.robot.Connect()):
                    print(f"[RobotConnect] OK intento {attempt}")
                    return True

                print(f"[RobotConnect] FALLO intento {attempt}/{ROBOT_CONNECT_RETRIES}")

            except Exception as exc:
                print(f"[RobotConnect][ERROR] intento {attempt}/{ROBOT_CONNECT_RETRIES}: {exc}")

        print("[RobotConnect] FALLO definitivo")
        return False
    def dashboard_command(self, command: str, timeout_s: float = 0.5) -> bool:
        if self.simulate or self.dry_run:
            print(f"[Dashboard][SIM] {command}")
            return True

        cmd = str(command).strip()
        if not cmd:
            return False

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout_s)
                s.connect((self.ROBOT_IP, self.DASHBOARD_PORT))
                try:
                    s.recv(1024)
                except Exception:
                    pass
                s.sendall((cmd + "\n").encode("utf-8"))
                try:
                    reply = s.recv(1024)
                    if reply:
                        print(f"[Dashboard] {cmd} -> {reply.decode('utf-8', errors='ignore').strip()}")
                except Exception:
                    pass
            return True
        except Exception as exc:
            print(f"[Dashboard][AVISO] {cmd} fallo: {exc}")
            return False
    def pause_robot_motion(self) -> bool:
        did_something = False

        robot = getattr(self, "robot", None)
        rdk = getattr(self, "RDK", None)

        for label, fn_name in (("robot.Pause", "Pause"), ("robot.Stop", "Stop")):
            if robot is not None and hasattr(robot, fn_name):
                try:
                    getattr(robot, fn_name)()
                    print(f"[Safety] {label} ejecutado.")
                    did_something = True
                except Exception as exc:
                    print(f"[Safety][AVISO] {label} fallo: {exc}")

        for label, fn_name in (("RDK.Pause", "Pause"), ("RDK.Stop", "Stop")):
            if rdk is not None and hasattr(rdk, fn_name):
                try:
                    getattr(rdk, fn_name)()
                    print(f"[Safety] {label} ejecutado.")
                    did_something = True
                except Exception as exc:
                    print(f"[Safety][AVISO] {label} fallo: {exc}")

        if self.dashboard_command("pause"):
            did_something = True

        self.runtime_pause_active = did_something or self.runtime_pause_active
        return did_something
    def resume_robot_motion(self) -> bool:
        if not self.runtime_pause_active:
            return True

        ok = self.dashboard_command("play")
        if ok:
            print("[Safety] Reanudacion enviada al robot.")
            self.runtime_pause_active = False
        else:
            print("[Safety][AVISO] No se pudo reanudar con dashboard play.")
        return ok
    def robot_call(self, context: str, fn: Callable[[], Any]) -> bool:
        if not self.assert_robot_ready(context):
            return False
        if self.dry_run:
            print(f"     [DRY_RUN] {context}")
            return True

        try:
            result = fn()
            if result is False:
                raise RuntimeError(f"{context} devolvió False")
            return True
        except Exception as exc:
            print(f"[{context}][ERROR] {exc}")
            self.enter_robot_safety_stop(context, exc)
            return False
    def sequence(self, label: str, *steps: Callable[[], bool]) -> bool:
        """Ejecuta pasos en orden y corta al primer fallo.

        Permite escribir las funciones como:
            return self.sequence("PickLid", step1, step2, step3)
        sin llenar cada función con if not ... return False.
        """
        print(label)
        for step in steps:
            if self.stop_cycle_if_needed(label):
                return False
            if step() is False:
                return False
        return not self.robot_safety_stop_active
    def check_required_robodk_items(self) -> List[str]:
        missing = []
        print("[RoboDK] Comprobando targets, frames y programas obligatorios...")

        for name in REQUIRED_TARGET_NAMES:
            if not self.RDK.Item(name, ITEM_TYPE_TARGET).Valid():
                missing.append(f"target:{name}")
                print(f"[RoboDK][AVISO] Falta target/posición: {name}")

        for name in REQUIRED_FRAME_NAMES:
            if not self.RDK.Item(name, ITEM_TYPE_FRAME).Valid():
                missing.append(f"frame:{name}")
                print(f"[RoboDK][AVISO] Falta frame reference: {name}")

        for name in GRIPPER_ROBODK_PROGRAMS:
            if not self.RDK.Item(name, ITEM_TYPE_PROGRAM).Valid():
                missing.append(f"program:{name}")
                print(f"[RoboDK][AVISO] Falta programa RoboDK: {name}")

        if not missing:
            print("[RoboDK] Todos los elementos obligatorios están presentes.")
        return missing
    def get_target(self, name: str):
        target = self.RDK.Item(name, ITEM_TYPE_TARGET)
        if not target.Valid():
            raise RuntimeError(f"Target {name!r} no encontrado")
        return target
    def get_frame(self, name: str):
        frame = self.RDK.Item(name, ITEM_TYPE_FRAME)
        if not frame.Valid():
            raise RuntimeError(f"Frame {name!r} no encontrado")
        return frame
    def set_frame(self, name: str) -> bool:
        return self.robot_call(f"set_frame:{name}", lambda: self.robot.setFrame(self.get_frame(name)))
    def apply_configured_motion_speed(self, context: str = "motion") -> bool:
        if self.dry_run:
            return True

        robot = getattr(self, "robot", None)
        if robot is None or not robot.Valid():
            return False

        speed = build_robot_motion_speed(getattr(self, "robot_speed_percent", ROBOT_SPEED_PERCENT_DEFAULT))
        apply_robot_motion_speed(robot, speed)
        self.robot_speed_percent = speed.percent
        return True
    def movej_target(self, name: str) -> bool:
        def _move():
            if not self.apply_configured_motion_speed(f"MoveJ:{name}"):
                return False
            return self.robot.MoveJ(self.get_target(name))
        return self.robot_call(f"MoveJ:{name}", _move)
    def movel_target(self, name: str) -> bool:
        def _move():
            if not self.apply_configured_motion_speed(f"MoveL:{name}"):
                return False
            return self.robot.MoveL(self.get_target(name))
        return self.robot_call(f"MoveL:{name}", _move)
    def movej_pose(self, pose, context: str) -> bool:
        def _move():
            if not self.apply_configured_motion_speed(f"MoveJ:{context}"):
                return False
            return self.robot.MoveJ(pose)
        return self.robot_call(f"MoveJ:{context}", _move)
    def movel_pose(self, pose, context: str) -> bool:
        def _move():
            if not self.apply_configured_motion_speed(f"MoveL:{context}"):
                return False
            return self.robot.MoveL(pose)
        return self.robot_call(f"MoveL:{context}", _move)
    def movel_target_with_local_z_offset(self, name: str, z_offset_mm: float, context: Optional[str] = None) -> bool:
        target = self.get_target(name)
        xyzrxyz = list(Pose_2_TxyzRxyz(target.Pose()))
        xyzrxyz[2] = float(xyzrxyz[2]) + float(z_offset_mm)
        pose = TxyzRxyz_2_Pose(xyzrxyz)
        move_context = context or f"{name}+Z{z_offset_mm:.1f}mm"
        return self.movel_pose(pose, move_context)
    def movel_target_with_global_z_offset(self, name: str, z_offset_mm: float, context: Optional[str] = None) -> bool:
        target = self.get_target(name)
        move_context = context or f"{name}+GLOBAL_Z{z_offset_mm:.1f}mm"

        if hasattr(target, "PoseAbs"):
            try:
                xyzrxyz = list(Pose_2_TxyzRxyz(target.PoseAbs()))
                xyzrxyz[2] = float(xyzrxyz[2]) + float(z_offset_mm)
                pose = TxyzRxyz_2_Pose(xyzrxyz)
                return self.movel_pose(pose, move_context)
            except Exception as exc:
                print(f"[MoveL][AVISO] No se pudo usar offset global Z en {name}: {exc}. Uso offset local.")

        return self.movel_target_with_local_z_offset(name, z_offset_mm, context=move_context)
    def target_xyzrxyz(self, name: str) -> List[float]:
        return list(Pose_2_TxyzRxyz(self.get_target(name).Pose()))
    def wait_move(self, context: str = "WaitMove") -> bool:
        return self.robot_call(context, lambda: self.robot.WaitMove())
    def run_program(self, name: str) -> bool:
        if not self.assert_robot_ready(f"run:{name}"):
            return False
        if self.dry_run:
            print(f"     [DRY_RUN] Programa RoboDK {name}")
            return True

        prog = self.RDK.Item(name, ITEM_TYPE_PROGRAM)
        if not prog.Valid():
            print(f"[RoboDK][AVISO] No existe programa: {name}")
            return False

        def _run():
            print(f"  >> Ejecutando programa RoboDK: {name}")
            prog.RunProgram()
            try:
                prog.WaitFinished()
            except Exception:
                self.robot.WaitMove()

        return self.robot_call(f"run:{name}", _run)
    def run(self, nombre: str) -> bool:
        return self.run_program(nombre)
    def run_program_in_simulation(self, name: str) -> bool:
        if self.dry_run:
            print(f"     [DRY_RUN] Programa RoboDK en simulacion {name}")
            return True

        prog = self.RDK.Item(name, ITEM_TYPE_PROGRAM)
        if not prog.Valid():
            print(f"[RoboDK][AVISO] No existe programa: {name}")
            return False

        try:
            prev_mode = self.RDK.RunMode()
        except Exception:
            prev_mode = RUNMODE_SIMULATE if self.simulate else RUNMODE_RUN_ROBOT

        try:
            self.RDK.setRunMode(RUNMODE_SIMULATE)
            print(f"  >> Ejecutando programa RoboDK en SIMULACION: {name}")
            prog.RunProgram()
            try:
                prog.WaitFinished()
            except Exception:
                pass
            return True
        except Exception as exc:
            self.enter_robot_safety_stop(f"run_simulation:{name}", exc)
            return False
        finally:
            try:
                self.RDK.setRunMode(prev_mode)
            except Exception:
                pass
    def lock_visual_updates(self, reason: str = "") -> None:
        return None
    def unlock_visual_updates(self, reason: str = "") -> None:
        return None
    def lid_attach_program_from_color(self, color: str) -> Optional[str]:
        if color == "red":
            return "AttachLidRed"
        if color == "blue":
            return "AttachLidBlue"
        if color == "green":
            return "AttachLidGreen"
        return None
    def run_gripper_visual(self, robodk_program: str) -> bool:
        if self.dry_run:
            print(f"     [DRY_RUN] Gripper visual {robodk_program}")
            return True

        prog = self.RDK.Item(robodk_program, ITEM_TYPE_PROGRAM)
        if not prog.Valid():
            print(f"[Gripper][AVISO] No existe programa RoboDK: {robodk_program}")
            return False

        try:
            print(f"  >> Ejecutando programa gripper RoboDK: {robodk_program}")
            prog.RunProgram()
            try:
                prog.WaitFinished()
            except Exception:
                pass
            return True
        except Exception as exc:
            self.enter_robot_safety_stop(f"gripper_visual:{robodk_program}", exc)
            return False
    def reconnect_after_gripper(self, urp_name: str) -> bool:
        if self.simulate or self.dry_run:
            return True

        try:
            self.robot.Disconnect()
        except Exception:
            pass

        for attempt in range(1, GRIPPER_RECONNECT_RETRIES + 1):
            try:
                self.robot.setConnectionParams(self.ROBOT_IP, self.ROBODK_PORT, "", "", "")
                if bool(self.robot.Connect()):
                    if attempt > 1:
                        print(f"[Gripper:{urp_name}] Reconectado en intento {attempt}")
                    return True
            except Exception as exc:
                print(f"[Gripper:{urp_name}][AVISO] Reintento {attempt}: {exc}")

            time.sleep(GRIPPER_RECONNECT_DELAY_S)

        self.enter_robot_safety_stop(f"gripper:{urp_name}", RuntimeError("No se pudo reconectar tras gripper"))
        return False
    @staticmethod
    def gripper_program_settle_s(urp_name: str) -> float:
        settle_s = float(GRIPPER_PROGRAM_SETTLE_S)
        if urp_name in BRIDGE_GRIPPER_URP_NAMES:
            settle_s += float(BRIDGE_GRIPPER_EXTRA_SETTLE_S)
        return settle_s
    def run_gripper(self, urp_name: str, robodk_program: str) -> bool:
        if self.robot_safety_stop_active:
            print(f"[SEGURIDAD] Gripper bloqueado ({urp_name}). Esperando tecla 'r'.")
            return False

        print(f"[Gripper] Solicitud: URP={urp_name}, visual={robodk_program}")

        try:
            prev_mode = self.RDK.RunMode()
        except Exception:
            prev_mode = RUNMODE_RUN_ROBOT

        try:
            self.RDK.setRunMode(RUNMODE_SIMULATE)

            visual_ok = self.run_gripper_visual(robodk_program)
            print(f"[Gripper] Visual antes de URP: {visual_ok}")

            if self.simulate:
                return visual_ok

            if not self.dry_run:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    s.connect((self.ROBOT_IP, self.DASHBOARD_PORT))

                    try:
                        print("[Gripper][Dashboard]", s.recv(1024))
                    except Exception:
                        pass

                    cmd_load = f"load /programs/{urp_name}.urp\n"
                    print(f"[Gripper][Dashboard] {cmd_load.strip()}")
                    s.sendall(cmd_load.encode("utf-8"))

                    try:
                        print("[Gripper][Dashboard]", s.recv(1024))
                    except Exception:
                        pass

                    print("[Gripper][Dashboard] play")
                    s.sendall(b"play\n")

                    try:
                        print("[Gripper][Dashboard]", s.recv(1024))
                    except Exception:
                        pass

                    settle_s = self.gripper_program_settle_s(urp_name)
                    print(f"[Gripper][Dashboard] Esperando ejecucion URP: {settle_s:.1f}s")
                    time.sleep(settle_s)

                if not self.reconnect_after_gripper(urp_name):
                    return False

            visual_ok_after = self.run_gripper_visual(robodk_program)
            print(f"[Gripper] Visual despues de URP: {visual_ok_after}")

            return visual_ok_after

        except Exception as exc:
            self.enter_robot_safety_stop(f"gripper:{urp_name}", exc)
            return False

        finally:
            try:
                self.RDK.setRunMode(prev_mode)
            except Exception:
                pass
    def gripperresetact(self) -> bool:
        return self.run_gripper("gripperresetact", "OpenLid")
    def gripperopen(self) -> bool:
        return self.run_gripper("gripperopen", "OpenGripper")
    def bridgeopen(self) -> bool:
        return self.run_gripper("bridgeopen", "bridgeopen")
    def gripperclose(self) -> bool:
        return self.run_gripper("gripperclose", "CloseGripper")
    def grippercellopen(self) -> bool:
        return self.run_gripper("grippercellopen", "OpenCell")
    def grippercellclose(self) -> bool:
        return self.run_gripper("grippercellclose", "CloseCell")
    def gripperclosebridge(self) -> bool:
        return self.run_gripper("gripperclosebridge", "CloseBridge")
    def gripperlidopen(self) -> bool:
        return self.run_gripper("gripperlidopen", "OpenLid")
    def gripperlidclose(self, color: Optional[str] = None) -> bool:
        attach_program = self.lid_attach_program_from_color(color)

        if attach_program is not None:
            print(f"[GripperLidClose] Ejecutando attach visual previo: {attach_program}")

            try:
                prev_mode = self.RDK.RunMode()
            except Exception:
                prev_mode = RUNMODE_RUN_ROBOT

            try:
                self.RDK.setRunMode(RUNMODE_SIMULATE)

                if not self.run_gripper_visual(attach_program):
                    print(f"[GripperLidClose][AVISO] Falló {attach_program}")
                    return False

            finally:
                try:
                    self.RDK.setRunMode(prev_mode)
                except Exception:
                    pass
        else:
            print(f"[GripperLidClose][AVISO] Color de tapa no válido o no indicado: {color}")

        ok = self.run_gripper("gripperlidclose", "CloseLid")
        if ok and attach_program is not None:
            try:
                prev_mode = self.RDK.RunMode()
            except Exception:
                prev_mode = RUNMODE_RUN_ROBOT

            try:
                self.RDK.setRunMode(RUNMODE_SIMULATE)
                self.run_gripper_visual(attach_program)
            finally:
                try:
                    self.RDK.setRunMode(prev_mode)
                except Exception:
                    pass
        return ok
    def gripperlidout(self) -> bool: #No se usa en un principio
        return self.run_gripper("gripperlidout", "OutLid")
    def gripperact(self) -> bool:
        return self.run_gripper("gripperact", "OpenGripper")
    def startup_home_and_activate_gripper(self) -> bool:
        return self.sequence(
            "[StationLogic] Inicializando robot en Home y activando gripper...",
            lambda: self.movej_target("Home"),
            lambda: self.wait_move("Home"),
            self.gripperresetact,
        )
    def move_home(self) -> bool:
        return self.sequence(
            "[StationLogic] Moviendo robot a Home...",
            lambda: self.movej_target("Home"),
            lambda: self.wait_move("Home"),
        )
    def move_final_home(self) -> bool:
        return self.sequence(
            "[StationLogic] Ciclo completo. Moviendo robot a HomeUR10...",
            lambda: self.movej_target("HomeUR10"),
            lambda: self.wait_move("HomeUR10"),
        )
    def set_box_frame(self, box_slot: int) -> bool:
        return self.set_frame(f"Box{box_slot}")
    def set_cell_frame(self, rack_cell_slot: int) -> bool:
        return self.set_frame(f"cell{rack_cell_slot}")
    def set_lid_frame(self, lid_slot: int) -> bool:
        return self.set_frame(f"Lid{lid_slot}")
    def set_bridge_frame(self) -> bool:
        return self.set_frame(BRIDGE_FRAME_NAME)

    def set_cell_visual_z(self, box_slot: int, cell_num: int, z_mm: float) -> bool:
        """Ajusta la altura Z del objeto visual de la celda física correspondiente.

        Mantiene X/Y y rotaciones. Si no hay `robodk_updater` configurado devuelve True.
        """
        try:
            if getattr(self, "robodk_updater", None) is None:
                return True

            # Obtener nombre base físico Sxx desde la posición Box/Cell
            base_name = physical_cell_id_from_box_position(int(box_slot), int(cell_num))
            return bool(self.robodk_updater.set_item_global_z(base_name, float(z_mm)))
        except Exception as exc:
            print(f"[RoboDK][AVISO] set_cell_visual_z fallo para Box{box_slot} C{cell_num}: {exc}")
            return False

    def movej_target_if_exists(self, name: str) -> bool:
        """Move to a target if it exists in RoboDK; otherwise do nothing.

        Returns True if moved or skipped (no error), False on error.
        """
        try:
            if self.dry_run or self.simulate:
                # In simulation/dry-run we can still attempt a move for visuals
                try:
                    item = self.RDK.Item(name, ITEM_TYPE_TARGET)
                    if item.Valid():
                        return self.movej_target(name)
                    return True
                except Exception:
                    return True

            item = self.RDK.Item(name, ITEM_TYPE_TARGET)
            if not item.Valid():
                return True
            return self.movej_target(name)
        except Exception as exc:
            print(f"[MoveIfExists][AVISO] No se pudo MoveJ a {name}: {exc}")
            return False

    def set_visual_z_for_object(self, object_id: str, z_mm: float) -> bool:
        """Ajusta la Z global de un objeto por su nombre/ID en RoboDK."""
        try:
            if getattr(self, "robodk_updater", None) is None:
                return True
            if not object_id:
                return False
            return bool(self.robodk_updater.set_item_global_z(str(object_id), float(z_mm)))
        except Exception as exc:
            print(f"[RoboDK][AVISO] set_visual_z_for_object fallo para {object_id}: {exc}")
            return False
