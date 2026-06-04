"""Application entry point and UI loop.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import json
import time

import cv2
import numpy as np
from ultralytics import YOLO

from app_config import *
from app_utils import draw_text, load_json, save_image_unicode
from calibration import PieceStabilizer, load_camera_calibration, load_homography, undistort_frame
from camera_capture import WebcamCaptureWorker
from drawing import draw_bridge_state, draw_hand_overlay, draw_station_state, print_station_state
from final_slot_lock import FinalSlotLockManager
from frame_processing import process_frame
from robodk_live_updater import RoboDKLiveUpdater
from robot_worker import RobotLogicWorker
from safety_control import HandSafetyController, set_station_robot_speed
from station_bootstrap import StationBootstrapWorker
from station_logic import StationLogic
from vision_detection import (
    HandLandmarkerDetector,
    build_bridge_state,
    build_station_state,
    filter_detections_by_confidence,
)
from vision_worker import VisionProcessingWorker

def main():
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modelo principal no encontrado: {MODEL_PATH}")
    if not BRIDGE_MODEL_PATH.exists():
        raise FileNotFoundError(f"Modelo bridge no encontrado: {BRIDGE_MODEL_PATH}")

    print("Loading YOLO model...")
    model = YOLO(str(MODEL_PATH))
    print(f"Model loaded: {MODEL_PATH}")

    print("Loading bridge YOLO model...")
    bridge_model = YOLO(str(BRIDGE_MODEL_PATH))
    print(f"Bridge model loaded: {BRIDGE_MODEL_PATH}")
    print(f"Bridge model classes: {getattr(bridge_model, 'names', {})}")

    hand_detector = None
    if ENABLE_HAND_LANDMARKER:
        print("Loading Google Hand Landmarker model...")
        hand_detector = HandLandmarkerDetector(HAND_LANDMARKER_PATH)
        print(f"Hand model loaded: {HAND_LANDMARKER_PATH}")

    print("Loading ROIs...")
    rois_data = load_json(ROIS_JSON_PATH)
    print(f"ROIs loaded: {ROIS_JSON_PATH}")

    print("Loading camera calibration...")
    camera_matrix, dist_coeffs = load_camera_calibration(CALIBRATION_JSON_PATH)
    print(f"Camera calibration loaded: {CALIBRATION_JSON_PATH}")

    print("Loading bridge homography...")
    bridge_homography, bridge_homography_data = load_homography(BRIDGE_HOMOGRAPHY_JSON_PATH)
    print(
        "Bridge homography loaded: "
        f"{BRIDGE_HOMOGRAPHY_JSON_PATH} "
        f"(mean_error_mm={bridge_homography_data.get('mean_error_mm', 'n/a')})"
    )
    bridge_stabilizer = PieceStabilizer(
        distance_threshold=BRIDGE_STABILIZER_DISTANCE_THRESHOLD,
        alpha=BRIDGE_STABILIZER_ALPHA,
    )
    vision_worker = VisionProcessingWorker(
        model=model,
        bridge_model=bridge_model,
        hand_detector=hand_detector,
        rois_data=rois_data,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        bridge_homography=bridge_homography,
        bridge_homography_data=bridge_homography_data,
        bridge_stabilizer=bridge_stabilizer,
    )

    camera_worker = WebcamCaptureWorker()
    opened_camera_index = camera_worker.opened_camera_index
    fps = float(camera_worker._latest_fps)
    if fps <= 1:
        fps = float(CAMERA_FPS)

    time.sleep(0.1)
    frame_preview, _, _, _ = camera_worker.get_latest_frame()
    ret_preview = frame_preview is not None

    if SHOW_WINDOW:
        cv2.namedWindow("Vision Logic - YOLO + StationLogic", cv2.WINDOW_NORMAL)

    if SHOW_WINDOW and SHOW_CAMERA_BEFORE_ROBODK_INIT and ret_preview and frame_preview is not None:
        preview = frame_preview.copy()
        draw_text(preview, "Camara abierta - inicializando RoboDK/StationLogic...", 20, 30, (255, 255, 255), scale=0.7)
        cv2.imshow("Vision Logic - YOLO + StationLogic", preview)
        cv2.waitKey(1)

    writer = None
    if SAVE_OUTPUT_VIDEO:
        first_undistorted = undistort_frame(frame_preview, camera_matrix, dist_coeffs, alpha=UNDISTORT_ALPHA)
        height, width = first_undistorted.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(OUTPUT_VIDEO_PATH), fourcc, fps, (width, height))

    robodk_updater = None
    station_logic = None
    station_bootstrap = None
    station_bootstrap_announced_ready = False
    station_bootstrap_failed = False
    final_slot_lock_manager = FinalSlotLockManager()

    if ASYNC_ROBODK_INIT and (ENABLE_ROBODK_LIVE_UPDATE or ENABLE_STATION_LOGIC):
        print("Arrancando RoboDK/StationLogic en segundo plano...")
        station_bootstrap = StationBootstrapWorker()
        station_bootstrap.start()
        robot_speed_percent = ROBOT_SPEED_PERCENT_DEFAULT
    else:
        if ENABLE_ROBODK_LIVE_UPDATE:
            print("Conectando con RoboDK live updater...")
            robodk_updater = RoboDKLiveUpdater()
            print("RoboDK live updater listo.")

        if ENABLE_STATION_LOGIC:
            print("Inicializando StationLogic...")
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
            final_slot_lock_manager.bind_station_logic(station_logic)

            if RUN_REPLACE_ALL_ON_START:
                print(f"Ejecutando programa inicial de RoboDK: {REPLACE_ALL_PROGRAM_NAME}")
                replace_all_ok = station_logic.run_program_in_simulation(REPLACE_ALL_PROGRAM_NAME)
                if not replace_all_ok:
                    print(f"[RoboDK][AVISO] No se pudo ejecutar {REPLACE_ALL_PROGRAM_NAME}")
                elif robodk_updater is not None:
                    print("[RoboDK] Refrescando cache de objetos tras Replace All...")
                    robodk_updater.refresh_all_items()

            if not STATION_SIMULATION_MODE and not STATION_DRY_RUN:
                station_logic.connect_robot()

            robot_speed_percent = set_station_robot_speed(station_logic, ROBOT_SPEED_PERCENT_DEFAULT)

            if MOVE_HOME_ON_START:
                set_station_robot_speed(station_logic, ROBOT_STARTUP_HOME_SPEED_PERCENT)
                station_logic.startup_home_and_activate_gripper()
                robot_speed_percent = set_station_robot_speed(station_logic, ROBOT_SPEED_PERCENT_DEFAULT)

            print("StationLogic lista.")
        else:
            robot_speed_percent = ROBOT_SPEED_PERCENT_DEFAULT

    hand_safety_controller = None
    if ENABLE_HAND_LANDMARKER:
        hand_safety_controller = HandSafetyController(
            station_logic,
            ROBOT_SPEED_PERCENT_DEFAULT,
            robot_worker=None,
        )
        hand_safety_controller.applied_speed_percent = robot_speed_percent

    robot_worker = None
    if (not ASYNC_ROBODK_INIT) and (station_logic is not None or robodk_updater is not None):
        robot_worker = RobotLogicWorker(
            station_logic=station_logic,
            robodk_updater=robodk_updater,
            vision_settle_s=VISION_SETTLE_AFTER_ROBOT_ACTION_S,
        )
        if hand_safety_controller is not None:
            hand_safety_controller.robot_worker = robot_worker
        print("Worker StationLogic/RoboDK iniciado en segundo hilo.")

    print("\n=== Vision Logic: YOLO -> StationLogic -> RoboDK ===")
    print(f"CÃ¡mara: Ã­ndice {opened_camera_index}")
    print(f"Modelo: {MODEL_PATH}")
    print(f"Modelo bridge: {BRIDGE_MODEL_PATH}")
    print(f"Modelo mano: {'DISABLED' if not ENABLE_HAND_LANDMARKER else HAND_LANDMARKER_PATH}")
    print(f"ROIs: {ROIS_JSON_PATH}")
    print("\nControles:")
    print("q / ESC -> salir")
    print("p       -> pausa")
    print("s       -> captura + print results")
    print("r       -> confirmar zona segura y reconectar robot")
    print("+ / -   -> subir/bajar velocidad base robot")
    print("1/2/3/4 -> velocidad base 10/25/50/100%")
    print("Mano: deteccion informativa; sin parada ni velocidad automatica\n")
    print(f"Display processed frame: {DISPLAY_PROCESSED_FRAME}")
    print(f"Draw live overlays: {DRAW_LIVE_VISION_OVERLAYS}\n")

    paused = False
    frame_idx = 0
    last_output = None
    last_results = None
    last_status_snapshot = None
    hand_on_camera = False
    hand_on_green = False
    hand_on_red = False
    latest_display_frame = frame_preview.copy() if ret_preview and frame_preview is not None else None
    last_processed_output = None
    last_packet_ts = 0.0
    last_bootstrap_status = "IDLE"
    last_visual_results = None
    last_visual_detections = []
    last_visual_bridge_detections = []
    last_visual_hand_state = None

    def apply_user_robot_speed(speed_percent):
        nonlocal robot_speed_percent
        speed_percent = max(
            ROBOT_SPEED_PERCENT_MIN,
            min(ROBOT_SPEED_PERCENT_MAX, float(speed_percent)),
        )

        try:
            # Siempre aplicar la velocidad directamente al robot; HandSafetyController
            # solo almacena estado de mano y no deberá controlar velocidad.
            if hand_safety_controller is not None:
                hand_safety_controller.set_normal_speed(speed_percent)
            robot_speed_percent = set_station_robot_speed(
                station_logic,
                speed_percent,
                robot_worker=robot_worker,
            )
            print(f"[RobotSpeed] Velocidad base solicitada = {robot_speed_percent:.0f}%")
        except Exception as exc:
            print(f"[RobotSpeed][ERROR] No se pudo cambiar velocidad, continuo sin cerrar: {exc}")

        return robot_speed_percent

    while True:
        try:
            if station_bootstrap is not None and not station_bootstrap_failed:
                bootstrap_state = station_bootstrap.poll()
                last_bootstrap_status = bootstrap_state.get("status", last_bootstrap_status)
                bootstrap_payload = bootstrap_state.get("payload")

                if bootstrap_payload is not None:
                    robodk_updater = bootstrap_payload.get("robodk_updater")
                    station_logic = bootstrap_payload.get("station_logic")
                    final_slot_lock_manager.bind_station_logic(station_logic)
                    robot_speed_percent = set_station_robot_speed(station_logic, ROBOT_SPEED_PERCENT_DEFAULT)
                    if hand_safety_controller is not None:
                        hand_safety_controller.station_logic = station_logic
                        hand_safety_controller.robot_worker = robot_worker
                        hand_safety_controller.applied_speed_percent = robot_speed_percent

                    if MOVE_HOME_ON_START and station_logic is not None:
                        set_station_robot_speed(station_logic, ROBOT_STARTUP_HOME_SPEED_PERCENT)
                        station_logic.startup_home_and_activate_gripper()
                        robot_speed_percent = set_station_robot_speed(station_logic, ROBOT_SPEED_PERCENT_DEFAULT)

                    if robot_worker is None and (station_logic is not None or robodk_updater is not None):
                        robot_worker = RobotLogicWorker(
                            station_logic=station_logic,
                            robodk_updater=robodk_updater,
                            vision_settle_s=VISION_SETTLE_AFTER_ROBOT_ACTION_S,
                        )
                        if hand_safety_controller is not None:
                            hand_safety_controller.robot_worker = robot_worker
                        print("Worker StationLogic/RoboDK iniciado en segundo hilo.")

                if bootstrap_state.get("done") and bootstrap_state.get("status") == "READY" and not station_bootstrap_announced_ready:
                    print("RoboDK/StationLogic listos.")
                    station_bootstrap_announced_ready = True

                if bootstrap_state.get("done") and bootstrap_state.get("status") == "ERROR":
                    station_bootstrap_failed = True
                    print(f"[Bootstrap][ERROR] {bootstrap_state.get('error')}")

            frame, opened_camera_index, _, camera_error = camera_worker.get_latest_frame()
            if frame is None:
                wait_frame = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=np.uint8)
                draw_text(wait_frame, "Esperando frames de camara...", 20, 40, (255, 255, 255), scale=0.8)
                if camera_error:
                    draw_text(wait_frame, camera_error, 20, 80, (0, 0, 255), scale=0.6)
                latest_display_frame = wait_frame
                if SHOW_WINDOW:
                    cv2.imshow("Vision Logic - YOLO + StationLogic", latest_display_frame)
                key = cv2.waitKey(30) & 0xFF
                if key in [ord("q"), ord("Q"), 27]:
                    break
                elif key in [ord("p"), ord("P")]:
                    paused = not paused
                    print("Pausa:", paused)
                continue

            latest_display_frame = frame

            if not paused:
                vision_worker.submit(frame)

            packet = vision_worker.consume_latest_packet()
            if packet is not None:
                output = packet["output"]
                results = packet["results"]
                detections = packet["detections"]
                bridge_detections = packet["bridge_detections"]
                robot_state = packet["robot_state"]
                hand_state = packet["hand_state"]

                hand_on_camera = bool(hand_state["hand_on_camera"])
                hand_on_green = bool(hand_state["hand_on_green"])
                hand_on_red = bool(hand_state["hand_on_red"])
                combined_red_zone = hand_on_red
                locked_results = final_slot_lock_manager.apply(results)
                robodk_results = build_station_state(
                    filter_detections_by_confidence(detections, ROBODK_MIN_CONFIDENCE),
                    rois_data,
                )
                robodk_results = final_slot_lock_manager.apply(robodk_results)
                for slot_id in RACK_SLOT_IDS:
                    logic_slot = locked_results.get(slot_id, {}) or {}
                    if bool(logic_slot.get("confirmed_open", False)):
                        # Keep open-box cell visuals aligned with the state
                        # StationLogic is allowed to process.
                        robodk_results.setdefault(slot_id, {})["battery_slots"] = (
                            logic_slot.get("battery_slots", {}) or {}
                        )
                robodk_results["bridge"] = build_bridge_state(bridge_detections)

                if station_logic is not None:
                    # Pasar tambien el estado de mano para que StationLogic pueda
                    # decidir esperar si hay una mano presente.
                    station_logic.update_camera_memory(locked_results, hand_state)
                    if hand_safety_controller is not None and hasattr(station_logic, "set_cell_treatment_lock"):
                        station_logic.set_cell_treatment_lock(combined_red_zone, locked_results)

                if hand_safety_controller is not None:
                    # Only record hand state; do not change robot speed here.
                    hand_safety_controller.apply(hand_state)
                last_output = output
                last_results = locked_results
                last_processed_output = output
                last_packet_ts = time.time()
                last_visual_results = locked_results
                last_visual_detections = detections
                last_visual_bridge_detections = bridge_detections
                last_visual_hand_state = hand_state
                last_status_snapshot = {
                    "hand_on_camera": hand_on_camera,
                    "hand_on_green": hand_on_green,
                    "hand_on_red": hand_on_red,
                    "robot_speed_percent": robot_speed_percent,
                }

                if robot_worker is not None:
                    robot_worker.submit(
                        station_results=locked_results,
                        robodk_results=robodk_results,
                        robot_red_zone_active=combined_red_zone,
                    )

                if PRINT_STATE_EVERY_N_FRAMES > 0 and frame_idx % PRINT_STATE_EVERY_N_FRAMES == 0:
                    print_station_state(locked_results)

                frame_idx += 1

                if station_logic is not None and getattr(station_logic, "shutdown_requested", False):
                    print("[Main] StationLogic solicito cierre del programa.")
                    break

            display_source = latest_display_frame if latest_display_frame is not None else frame
            if DISPLAY_PROCESSED_FRAME and last_processed_output is not None:
                display_source = last_processed_output
            display_frame = display_source.copy()

            if (
                DRAW_LIVE_VISION_OVERLAYS
                and not DISPLAY_PROCESSED_FRAME
                and last_visual_results is not None
            ):
                draw_station_state(display_frame, last_visual_results, rois_data)
                draw_bridge_state(display_frame, last_visual_results.get("bridge"), last_visual_bridge_detections)
                draw_hand_overlay(display_frame, last_visual_hand_state)

            draw_text(display_frame, f"Frame: {frame_idx}", 20, 30, (255, 255, 255), scale=0.7)
            draw_text(display_frame, "YOLO -> StationLogic.update(results) -> RoboDK", 20, 60, (255, 255, 255), scale=0.52)
            draw_text(display_frame, "q: salir | p: pausa | s: captura | r: reconectar seguro", 20, 88, (255, 255, 255), scale=0.52)

            status_y = 116
            hand_status = (
                f"hand_on_camera={hand_on_camera} | "
                f"hand_on_green={hand_on_green} | "
                f"hand_on_red={hand_on_red}"
            )
            hand_status_color = (0, 0, 255) if hand_on_red else ((0, 255, 0) if hand_on_green else (180, 180, 180))
            draw_text(display_frame, hand_status, 20, status_y, hand_status_color, scale=0.52)
            status_y += 28

            processing_text = "VISION: PAUSED" if paused else ("VISION: PROCESSING" if vision_worker.is_busy() else "VISION: READY")
            draw_text(display_frame, processing_text, 20, status_y, (255, 255, 255), scale=0.52)
            status_y += 28

            if not DISPLAY_PROCESSED_FRAME:
                packet_age = 0.0 if last_packet_ts <= 0 else (time.time() - last_packet_ts)
                draw_text(display_frame, f"Display=LIVE CAMERA | vision_age={packet_age:.2f}s", 20, status_y, (0, 200, 255), scale=0.52)
                status_y += 28

            if camera_error:
                draw_text(display_frame, camera_error, 20, status_y, (0, 0, 255), scale=0.5)
                status_y += 24

            if robot_worker is not None:
                draw_text(display_frame, robot_worker.status_text(), 20, status_y, (255, 255, 255), scale=0.52)
                status_y += 28

            if station_logic is not None and hasattr(station_logic, "safety_status_text"):
                safety_text = station_logic.safety_status_text()
                if safety_text != "ROBOT: OK":
                    draw_text(display_frame, safety_text, 20, status_y, (0, 0, 255), scale=0.52)
                    status_y += 28

            if station_bootstrap is not None and not station_bootstrap_announced_ready and not station_bootstrap_failed:
                draw_text(display_frame, f"RoboDK init: {last_bootstrap_status}", 20, status_y, (0, 200, 255), scale=0.52)
                status_y += 28

            if station_bootstrap_failed:
                draw_text(display_frame, "RoboDK init fallo; vision sigue activa", 20, status_y, (0, 0, 255), scale=0.52)
                status_y += 28

            draw_text(display_frame, f"Robot speed: {robot_speed_percent:.0f}%", 20, status_y, (255, 255, 255), scale=0.52)

            if writer is not None:
                writer.write(display_frame)

            if SHOW_WINDOW:
                cv2.imshow("Vision Logic - YOLO + StationLogic", display_frame)

        except Exception as exc:
            print(f"[MainLoop][ERROR] {exc}")
            time.sleep(0.05)
            continue

        key = cv2.waitKey(1 if not paused else 30) & 0xFF

        if key in [ord("q"), ord("Q"), 27]:
            break
        elif key in [ord("p"), ord("P")]:
            paused = not paused
            print("Pausa:", paused)
        elif key in [ord("+"), ord("=")]:
            apply_user_robot_speed(robot_speed_percent + ROBOT_SPEED_PERCENT_STEP)
        elif key in [ord("-"), ord("_")]:
            apply_user_robot_speed(robot_speed_percent - ROBOT_SPEED_PERCENT_STEP)
        elif key == ord("1"):
            apply_user_robot_speed(10.0)
        elif key == ord("2"):
            apply_user_robot_speed(25.0)
        elif key == ord("3"):
            apply_user_robot_speed(50.0)
        elif key == ord("4"):
            apply_user_robot_speed(100.0)
        elif key in [ord("r"), ord("R")]:
            if station_logic is None:
                print("[SEGURIDAD][AVISO] StationLogic no estÃ¡ inicializado; no puedo reconectar.")
            elif robot_worker is not None:
                robot_worker.request_acknowledge_safe_reconnect(wait=False)
            else:
                station_logic.acknowledge_robot_safe_and_reconnect()
        elif key in [ord("s"), ord("S")]:
            if last_output is not None:
                capture_path = OUTPUT_FOLDER / f"captura_vision_logic_{frame_idx:06d}.png"
                save_image_unicode(capture_path, last_output)
                print(f"Captura guardada: {capture_path}")
            if last_results is not None:
                payload = {
                    "station_state": last_results,
                    "safety_state": last_status_snapshot,
                }
                print("\nResultados enviados a StationLogic + estados de seguridad:")
                print(json.dumps(payload, indent=4, ensure_ascii=False))

    if station_logic is not None:
        try:
            print("[Main] Llevando robot a HomeUR10 antes de cerrar...")
            station_logic.move_final_home()
        except Exception as exc:
            print(f"[Main][AVISO] No se pudo mover a HomeUR10 al cerrar: {exc}")

    if robot_worker is not None:
        print("Deteniendo worker StationLogic/RoboDK...")
        robot_worker.stop()
    if vision_worker is not None:
        print("Deteniendo worker de visión...")
        vision_worker.stop()
    if camera_worker is not None:
        print("Deteniendo worker de cámara...")
        camera_worker.stop()
    if writer is not None:
        writer.release()
        print(f"Ví­deo guardado en: {OUTPUT_VIDEO_PATH}")
    cv2.destroyAllWindows()
