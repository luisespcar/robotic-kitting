"""Single-frame vision pipeline orchestration.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

from app_config import *
from calibration import (
    filter_bridge_detections_inside_homography,
    finalize_bridge_detections_coordinates,
    undistort_frame,
)
from drawing import draw_bridge_state, draw_hand_overlay, draw_station_state
from vision_detection import (
    analyze_hand_presence,
    build_bridge_state,
    build_station_state,
    get_robot_zone_divider_y,
    yolo_result_to_bridge_detections,
    yolo_result_to_detections,
)

def process_frame(
    model,
    bridge_model,
    hand_detector,
    frame,
    rois_data,
    camera_matrix,
    dist_coeffs,
    bridge_homography,
    bridge_homography_data,
    bridge_stabilizer,
):
    frame_undistorted = undistort_frame(frame, camera_matrix, dist_coeffs, alpha=UNDISTORT_ALPHA)

    yolo_results = model.predict(
        source=frame_undistorted,
        imgsz=IMG_SIZE,
        conf=CONFIDENCE,
        device=DEVICE,
        verbose=False,
    )

    result = yolo_results[0]
    detections = yolo_result_to_detections(result)
    station_state = build_station_state(detections, rois_data)

    bridge_yolo_results = bridge_model.predict(
        source=frame_undistorted,
        imgsz=IMG_SIZE,
        conf=BRIDGE_CONFIDENCE,
        iou=BRIDGE_IOU,
        max_det=BRIDGE_MAX_DET,
        agnostic_nms=False,
        retina_masks=True,
        device=DEVICE,
        verbose=False,
    )
    bridge_result = bridge_yolo_results[0]
    bridge_detections = yolo_result_to_bridge_detections(
        bridge_result,
        frame_undistorted.shape,
        bridge_homography,
    )
    bridge_detections = filter_bridge_detections_inside_homography(
        bridge_detections,
        bridge_homography_data,
    )
    if BRIDGE_DEBUG_PRINT_EVERY_N_FRAMES > 0:
        process_frame._bridge_debug_counter = getattr(process_frame, "_bridge_debug_counter", 0) + 1
        if process_frame._bridge_debug_counter % BRIDGE_DEBUG_PRINT_EVERY_N_FRAMES == 0:
            raw_boxes = 0 if getattr(bridge_result, "boxes", None) is None else len(bridge_result.boxes)
            has_masks = bool(
                getattr(getattr(bridge_result, "masks", None), "data", None) is not None
            )
            print(
                f"[BridgeDebug] raw_boxes={raw_boxes} has_masks={has_masks} "
                f"parsed={len(bridge_detections)} "
                f"names={[str(bridge_result.names[int(box.cls[0])]) for box in bridge_result.boxes] if getattr(bridge_result, 'boxes', None) is not None else []}"
            )
    robot_detections = []
    robot_state = {
        "robot_on_camera": False,
        "robot_green_zone": False,
        "robot_red_zone": False,
        "robot_center": None,
        "zone_divider_y": get_robot_zone_divider_y(rois_data, frame_undistorted.shape),
        "best_robot_detection": None,
    }

    bridge_detections = bridge_stabilizer.stabilize(bridge_detections)
    bridge_detections = filter_bridge_detections_inside_homography(
        bridge_detections,
        bridge_homography_data,
    )
    bridge_detections = finalize_bridge_detections_coordinates(bridge_detections, bridge_homography_data)

    station_state["bridge"] = build_bridge_state(bridge_detections)

    hand_state = {
        "hand_on_camera": False,
        "hand_on_green": False,
        "hand_on_red": False,
        "hand_center": None,
        "hand_landmarks_px": None,
        "zone_divider_y": robot_state.get("zone_divider_y"),
    }
    if hand_detector is not None:
        hand_result = hand_detector.detect(frame_undistorted)
        hand_state = analyze_hand_presence(hand_result, frame_undistorted.shape, rois_data)

    output = frame_undistorted.copy()
    draw_station_state(output, station_state, rois_data)
    draw_bridge_state(output, station_state.get("bridge"), bridge_detections)
    draw_hand_overlay(output, hand_state)

    return output, station_state, detections, bridge_detections, robot_detections, robot_state, hand_state
