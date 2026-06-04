"""YOLO/MediaPipe parsing and station-state construction.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np

from app_config import *
from mediapipe_compat import mp, mp_python, mp_vision

def get_color_from_class(class_name):
    if class_name.endswith("_blue"):
        return "blue"
    if class_name.endswith("_green"):
        return "green"
    if class_name.endswith("_red"):
        return "red"
    return None


def point_inside_roi(px, py, roi):
    if roi is None:
        return False
    x, y, w, h = roi
    return x <= px <= x + w and y <= py <= y + h


def detection_center(det):
    contour = det.get("contour")
    if contour:
        xs = [float(pt[0]) for pt in contour]
        ys = [float(pt[1]) for pt in contour]
        return float(sum(xs) / len(xs)), float(sum(ys) / len(ys))

    x1, y1, x2, y2 = det["xyxy"]
    return (x1 + x2) / 2, (y1 + y2) / 2


def detection_inside_roi(det, roi):
    cx, cy = detection_center(det)
    return point_inside_roi(cx, cy, roi)


def find_best_detection_in_roi(detections, valid_classes, roi):
    candidates = []
    for det in detections:
        if det["class_name"] not in valid_classes:
            continue
        if detection_inside_roi(det, roi):
            candidates.append(det)
    if not candidates:
        return None
    candidates.sort(key=lambda d: d["conf"], reverse=True)
    return candidates[0]


def yolo_result_to_detections(result):
    detections = []
    names = result.names
    boxes = result.boxes
    if boxes is None:
        return detections
    mask_polygons = []
    if getattr(result, "masks", None) is not None and getattr(result.masks, "xy", None) is not None:
        mask_polygons = result.masks.xy

    for idx, box in enumerate(boxes):
        cls_id = int(box.cls[0])
        class_name = names[cls_id]
        conf = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        contour = None
        if idx < len(mask_polygons):
            polygon = mask_polygons[idx]
            if polygon is not None and len(polygon) >= 3:
                contour = [[float(px), float(py)] for px, py in polygon]
        detections.append({
            "class_id": cls_id,
            "class_name": class_name,
            "conf": conf,
            "xyxy": [float(x1), float(y1), float(x2), float(y2)],
            "contour": contour,
        })
    return detections


def normalize_angle(angle_deg):
    while angle_deg > 90.0:
        angle_deg -= 180.0
    while angle_deg < -90.0:
        angle_deg += 180.0
    return float(angle_deg)


def canonical_bridge_class_name(class_name):
    raw_name = str(class_name or "").strip()
    normalized = raw_name.lower().replace("-", "_").replace(" ", "_")

    if "small" in normalized or "pequ" in normalized:
        return "small"
    if "large" in normalized or "big" in normalized or "grande" in normalized:
        return "large"
    return None


def boxes_overlap(box1, box2, threshold=0.1):
    x1, y1, x2, y2 = box1
    x1b, y1b, x2b, y2b = box2

    xi1 = max(x1, x1b)
    yi1 = max(y1, y1b)
    xi2 = min(x2, x2b)
    yi2 = min(y2, y2b)

    inter_area = max(0.0, xi2 - xi1) * max(0.0, yi2 - yi1)
    area1 = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area2 = max(0.0, x2b - x1b) * max(0.0, y2b - y1b)
    union_area = area1 + area2 - inter_area
    iou = inter_area / union_area if union_area > 0.0 else 0.0
    return iou > float(threshold)


def mask_to_centroid_and_angle(mask):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < BRIDGE_MIN_MASK_AREA:
        return None

    moments = cv2.moments(contour)
    if abs(moments["m00"]) < 1e-6:
        return None

    cx = moments["m10"] / moments["m00"]
    cy = moments["m01"] / moments["m00"]
    rect = cv2.minAreaRect(contour)
    (_, _), (rw, rh), angle_deg = rect
    if rw < rh:
        angle_deg += 90.0
    angle_deg = normalize_angle(angle_deg + BRIDGE_ANGLE_OFFSET_DEG)

    return float(cx), float(cy), float(angle_deg), contour, rect


def box_to_centroid_and_angle(x1, y1, x2, y2):
    cx = (float(x1) + float(x2)) / 2.0
    cy = (float(y1) + float(y2)) / 2.0
    width = max(1.0, float(x2) - float(x1))
    height = max(1.0, float(y2) - float(y1))
    angle_deg = 0.0 if width >= height else 90.0
    contour = np.array(
        [
            [float(x1), float(y1)],
            [float(x2), float(y1)],
            [float(x2), float(y2)],
            [float(x1), float(y2)],
        ],
        dtype=np.float32,
    )
    rect = ((cx, cy), (width, height), angle_deg)
    return cx, cy, angle_deg, contour, rect


def yolo_result_to_bridge_detections(result, frame_shape, homography_matrix):
    detections = []
    names = result.names
    boxes = result.boxes
    masks = getattr(result, "masks", None)
    if boxes is None:
        return detections

    frame_h, frame_w = frame_shape[:2]
    mask_data = None
    if masks is not None and getattr(masks, "data", None) is not None:
        mask_data = masks.data.cpu().numpy()

    for idx, box in enumerate(boxes):
        cls_id = int(box.cls[0])
        raw_class_name = names[cls_id]
        class_name = canonical_bridge_class_name(raw_class_name)
        if class_name not in BRIDGE_CLASSES:
            continue

        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        mask = None
        if mask_data is not None and idx < len(mask_data):
            raw_mask = mask_data[idx]
            mask = (raw_mask > 0.5).astype(np.uint8) * 255
            mask = cv2.resize(mask, (frame_w, frame_h), interpolation=cv2.INTER_NEAREST)
            info = mask_to_centroid_and_angle(mask)
        else:
            info = box_to_centroid_and_angle(x1, y1, x2, y2)

        if info is None:
            continue

        cx, cy, angle_deg, contour, rect = info
        detections.append({
            "class_id": cls_id,
            "raw_class_name": str(raw_class_name),
            "class_name": class_name,
            "conf": float(box.conf[0]),
            "xyxy": [float(x1), float(y1), float(x2), float(y2)],
            "mask": mask,
            "has_mask": mask is not None,
            "centroid_px": [cx, cy],
            "center_bridge_mm_raw": [0.0, 0.0],
            "center_bridge_mm": [0.0, 0.0],
            "coordinate_frame": "Bridge",
            "rotation_deg": angle_deg,
            "contour": contour.reshape(-1, 2).astype(np.float32).tolist(),
            "rect": rect,
            "homography_matrix": homography_matrix,
        })

    detections.sort(key=lambda det: float(det.get("conf", 0.0)), reverse=True)
    return detections


def build_bridge_state(bridge_detections):
    pieces = []
    by_type = {}

    for det in bridge_detections or []:
        if det.get("inside_homography") is False:
            continue

        piece = {
            "type": det["class_name"],
            "raw_type": det.get("raw_class_name", det["class_name"]),
            "center_x_mm_raw": float(det.get("center_bridge_mm_raw", [0.0, 0.0])[0]),
            "center_y_mm_raw": float(det.get("center_bridge_mm_raw", [0.0, 0.0])[1]),
            "center_x_mm": float(det["center_bridge_mm"][0]),
            "center_y_mm": float(det["center_bridge_mm"][1]),
            "center_x_rdk_mm": float(det["center_bridge_mm"][0]),
            "center_y_rdk_mm": float(det["center_bridge_mm"][1]),
            "centroid_px": list(det.get("centroid_px", [0.0, 0.0])),
            "coordinate_frame": str(det.get("coordinate_frame", "Bridge")),
            "rotation_deg": float(det["rotation_deg"]),
            "confidence": float(det["conf"]),
            "inside_homography": bool(det.get("inside_homography", True)),
        }
        pieces.append(piece)
        by_type.setdefault(piece["type"], piece)

    return {
        "pieces": pieces,
        "small": by_type.get("small"),
        "large": by_type.get("large"),
    }


def find_best_detection(detections, valid_classes=None):
    candidates = []
    for det in detections:
        if valid_classes is not None and det["class_name"] not in valid_classes:
            continue
        candidates.append(det)

    if not candidates:
        return None

    candidates.sort(key=lambda d: d["conf"], reverse=True)
    return candidates[0]


def filter_detections_by_confidence(detections, min_confidence):
    return [det for det in (detections or []) if float(det.get("conf", 0.0)) >= float(min_confidence)]


def get_robot_zone_divider_y(rois_data, frame_shape, margin_px=10):
    frame_height = int(frame_shape[0])
    rack_slots = (rois_data or {}).get("rack_slots", {})
    divider_candidates = []

    for rack_data in rack_slots.values():
        roi_box = rack_data.get("roi_slot_box")
        if roi_box is None:
            continue
        _, y, _, h = roi_box
        divider_candidates.append(float(y + h + margin_px))

    if divider_candidates:
        return min(frame_height - 1.0, max(divider_candidates))

    return frame_height / 2.0


def analyze_robot_presence(robot_detections, frame_shape, rois_data):
    zone_divider_y = get_robot_zone_divider_y(rois_data, frame_shape)
    best_robot_detection = find_best_detection(robot_detections)

    robot_on_camera = best_robot_detection is not None
    robot_green_zone = False
    robot_red_zone = False
    robot_center = None

    if best_robot_detection is not None:
        robot_center = detection_center(best_robot_detection)
        _, center_y = robot_center
        robot_green_zone = center_y >= zone_divider_y
        robot_red_zone = center_y < zone_divider_y

    return {
        "robot_on_camera": robot_on_camera,
        "robot_green_zone": robot_green_zone,
        "robot_red_zone": robot_red_zone,
        "robot_center": robot_center,
        "zone_divider_y": zone_divider_y,
        "best_robot_detection": best_robot_detection,
    }


class HandLandmarkerDetector:
    def __init__(self, model_path):
        if mp is None or mp_python is None or mp_vision is None:
            raise ImportError(
                "MediaPipe no está instalado. Instala con: python -m pip install mediapipe"
            )

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Modelo de mano no encontrado: {model_path}")

        self.model_path = model_path
        self.resolved_model_path = self._resolve_model_path(model_path)
        base_options = mp_python.BaseOptions(model_asset_path=str(self.resolved_model_path))
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=HAND_MAX_NUM_HANDS,
            min_hand_detection_confidence=HAND_MIN_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=HAND_MIN_PRESENCE_CONFIDENCE,
            min_tracking_confidence=HAND_MIN_TRACKING_CONFIDENCE,
        )
        self.landmarker = mp_vision.HandLandmarker.create_from_options(options)

    def _resolve_model_path(self, model_path):
        try:
            str(model_path).encode("ascii")
            return model_path
        except UnicodeEncodeError:
            pass

        temp_dir = Path(tempfile.gettempdir()) / "visionlogic_mediapipe"
        temp_dir.mkdir(parents=True, exist_ok=True)
        safe_model_path = temp_dir / "hand_landmarker.task"

        source_stat = model_path.stat()
        needs_copy = True
        if safe_model_path.exists():
            safe_stat = safe_model_path.stat()
            needs_copy = (
                int(source_stat.st_size) != int(safe_stat.st_size)
                or int(source_stat.st_mtime) > int(safe_stat.st_mtime)
            )

        if needs_copy:
            shutil.copy2(model_path, safe_model_path)
            print(f"[HandLandmarker] Modelo copiado a ruta temporal segura: {safe_model_path}")

        return safe_model_path

    def detect(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        return self.landmarker.detect(mp_image)


def analyze_hand_presence(hand_result, frame_shape, rois_data):
    zone_divider_y = get_robot_zone_divider_y(rois_data, frame_shape)
    image_height, image_width = frame_shape[:2]
    hand_landmarks_list = getattr(hand_result, "hand_landmarks", None) or []
    handedness_list = getattr(hand_result, "handedness", None) or []

    hand_on_camera = False
    hand_on_green = False
    hand_on_red = False
    hand_center = None
    hand_landmarks_px = None
    hand_confidence = 0.0

    if hand_landmarks_list:
        if handedness_list and handedness_list[0]:
            hand_confidence = float(getattr(handedness_list[0][0], "score", 0.0) or 0.0)
        else:
            hand_confidence = 1.0

        hand_on_camera = hand_confidence >= HAND_SAFETY_CONFIDENCE_THRESHOLD
        landmarks = hand_landmarks_list[0]
        hand_landmarks_px = []
        for lm in landmarks:
            px = min(float(image_width - 1), max(0.0, float(lm.x) * image_width))
            py = min(float(image_height - 1), max(0.0, float(lm.y) * image_height))
            hand_landmarks_px.append((px, py))

        xs = [pt[0] for pt in hand_landmarks_px]
        ys = [pt[1] for pt in hand_landmarks_px]
        hand_center = (float(sum(xs) / len(xs)), float(sum(ys) / len(ys)))

        if hand_on_camera:
            _, center_y = hand_center
            hand_on_green = center_y < zone_divider_y
            hand_on_red = center_y >= zone_divider_y

    return {
        "hand_on_camera": hand_on_camera,
        "hand_on_green": hand_on_green,
        "hand_on_red": hand_on_red,
        "hand_center": hand_center,
        "hand_landmarks_px": hand_landmarks_px,
        "hand_confidence": hand_confidence,
        "zone_divider_y": zone_divider_y,
    }


def analyze_polarity(detections, battery_roi, terminal_expected_roi):
    terminal_in_expected = find_best_detection_in_roi(
        detections,
        TERMINAL_CLASSES,
        terminal_expected_roi,
    )
    if terminal_in_expected is not None:
        return True

    terminal_in_battery = find_best_detection_in_roi(
        detections,
        TERMINAL_CLASSES,
        battery_roi,
    )
    if terminal_in_battery is not None:
        return False

    return None


def build_station_state(detections, rois_data):
    """Construye exactamente los results que consume StationLogic.update(results)."""
    results = {}
    rack_slots = rois_data.get("rack_slots", {})

    for rack_id, rack_data in rack_slots.items():
        roi_box = rack_data.get("roi_slot_box")
        roi_lid = rack_data.get("roi_lid")

        box_det = find_best_detection_in_roi(detections, BOX_CLASSES, roi_box)
        lid_det = find_best_detection_in_roi(detections, LID_CLASSES, roi_lid)

        box_detected = box_det is not None
        lid_detected = lid_det is not None

        box_color = get_color_from_class(box_det["class_name"]) if box_det else None
        lid_color = get_color_from_class(lid_det["class_name"]) if lid_det else None

        if lid_detected:
            box_present = True
            box_state = "closed"
            confirmed_open = False

            # IMPORTANTE:
            # Mientras hay tapa, NO usamos el color de la caja para la lÃ³gica.
            # La caja real todavÃ­a no se considera fiable hasta que se quite la tapa.
            open_box_color = None
            detected_box_color = None
            closed_box_color = None

        elif box_detected:
            box_present = True
            box_state = "open"
            confirmed_open = True

            # Ahora sÃ­: sin tapa, el color de la caja es fiable.
            lid_color = None
            open_box_color = box_color
            detected_box_color = box_color
            closed_box_color = None

        else:
            box_present = False
            box_state = "empty"
            confirmed_open = False
            lid_color = None
            open_box_color = None
            detected_box_color = None
            closed_box_color = None


        results[rack_id] = {
            "box_present": box_present,
            "box_state": box_state,
            "confirmed_open": confirmed_open,
            "lid_color": lid_color,
            "closed_box_color": closed_box_color,
            "open_box_color": open_box_color,
            "box_detected": box_detected,
            "lid_detected": lid_detected,
            "detected_box_color": detected_box_color,
            "battery_slots": {},
        }

        for battery_id, battery_data in rack_data.get("battery_slots", {}).items():
            roi_battery = battery_data.get("roi_battery")
            roi_terminal_red = battery_data.get("roi_terminal_red")

            battery_det = find_best_detection_in_roi(detections, BATTERY_CLASSES, roi_battery)
            battery_present = battery_det is not None
            battery_color = get_color_from_class(battery_det["class_name"]) if battery_det else None

            polarity_ok = None
            if battery_present:
                polarity_ok = analyze_polarity(detections, roi_battery, roi_terminal_red)

            results[rack_id]["battery_slots"][battery_id] = {
                "battery_present": battery_present,
                "battery_color": battery_color,
                "polarity_ok": polarity_ok,
            }

    return results
