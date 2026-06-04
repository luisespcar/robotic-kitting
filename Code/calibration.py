"""Camera calibration, homography and bridge detection stabilization.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import cv2
import numpy as np

from app_config import BRIDGE_HOMOGRAPHY_PRINT_EVERY_N_FRAMES
from app_utils import load_json

def load_camera_calibration(json_path):
    calibration = load_json(json_path)
    camera_matrix = np.array(calibration["camera_matrix"], dtype=np.float64)
    dist_coeffs = np.array(calibration["distortion_coefficients"], dtype=np.float64)
    return camera_matrix, dist_coeffs


def undistort_frame(frame, camera_matrix, dist_coeffs, alpha=0):
    h, w = frame.shape[:2]
    new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
        camera_matrix,
        dist_coeffs,
        (w, h),
        alpha,
        (w, h),
    )
    return cv2.undistort(frame, camera_matrix, dist_coeffs, None, new_camera_matrix)


def load_homography(json_path):
    data = load_json(json_path)
    H = np.array(data["homography_pixel_to_robot"], dtype=np.float64)
    return H, data


def homography_image_polygon(homography_data):
    if not isinstance(homography_data, dict):
        return None

    image_points = homography_data.get("image_points")
    if not isinstance(image_points, list) or len(image_points) < 3:
        return None

    try:
        points = np.array(image_points, dtype=np.float32).reshape((-1, 2))
    except Exception:
        return None

    if len(points) < 3:
        return None

    return cv2.convexHull(points).reshape((-1, 1, 2))


def point_inside_homography_polygon(px, py, homography_data):
    polygon = homography_image_polygon(homography_data)
    if polygon is None:
        return True
    return cv2.pointPolygonTest(polygon, (float(px), float(py)), False) >= 0


def filter_bridge_detections_inside_homography(bridge_detections, homography_data):
    filtered = []
    for det in bridge_detections or []:
        centroid = det.get("centroid_px")
        if not centroid or len(centroid) < 2:
            det["inside_homography"] = False
            continue

        inside = point_inside_homography_polygon(centroid[0], centroid[1], homography_data)
        det["inside_homography"] = bool(inside)
        if inside:
            filtered.append(det)

    return filtered


def pixel_to_robot(u, v, H):
    point = np.array([[[float(u), float(v)]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(point, H)
    x_robot, y_robot = transformed[0][0]
    return float(x_robot), float(y_robot)


def piecewise_affine_pixel_to_robot(u, v, homography_data):
    if not isinstance(homography_data, dict):
        return None
    if homography_data.get("mapping_method") != "piecewise_affine":
        return None

    image_points = np.asarray(homography_data.get("image_points", []), dtype=np.float64)
    robot_points = np.asarray(homography_data.get("robot_points_mm", []), dtype=np.float64)
    triangles = homography_data.get("piecewise_triangles", [])
    if image_points.ndim != 2 or image_points.shape[1:] != (2,) or image_points.shape != robot_points.shape:
        return None

    query = np.array([float(u), float(v), 1.0], dtype=np.float64)
    for indices in triangles:
        if not isinstance(indices, list) or len(indices) != 3:
            continue
        try:
            source_triangle = image_points[indices]
            weights = np.linalg.solve(
                np.vstack((source_triangle.T, np.ones(3, dtype=np.float64))),
                query,
            )
        except (IndexError, np.linalg.LinAlgError):
            continue

        if np.all(weights >= -1e-6):
            x_robot, y_robot = weights @ robot_points[indices]
            return float(x_robot), float(y_robot)

    return None


def bridge_pixel_to_bridge_mm(u, v, H, homography_data=None):
    mapped_point = piecewise_affine_pixel_to_robot(u, v, homography_data)
    if mapped_point is not None:
        return mapped_point

    x_bridge_mm, y_bridge_mm = pixel_to_robot(u, v, H)
    return float(x_bridge_mm), float(y_bridge_mm)


def finalize_bridge_detections_coordinates(bridge_detections, homography_data=None):
    debug_counter = getattr(finalize_bridge_detections_coordinates, "_debug_counter", 0) + 1
    finalize_bridge_detections_coordinates._debug_counter = debug_counter
    should_print_homography = (
        BRIDGE_HOMOGRAPHY_PRINT_EVERY_N_FRAMES > 0
        and debug_counter % BRIDGE_HOMOGRAPHY_PRINT_EVERY_N_FRAMES == 0
    )

    for det in bridge_detections or []:
        cx, cy = det["centroid_px"]
        x_bridge_mm_raw, y_bridge_mm_raw = bridge_pixel_to_bridge_mm(
            cx,
            cy,
            det["homography_matrix"],
            homography_data,
        )
        det["center_bridge_mm_raw"] = [x_bridge_mm_raw, y_bridge_mm_raw]
        det["center_bridge_mm"] = [x_bridge_mm_raw, y_bridge_mm_raw]

        if should_print_homography:
            print(
                f"[BridgeHomography] type={det['class_name']} "
                f"centroid_px=({cx:.1f}, {cy:.1f}) "
                f"after_homography=({x_bridge_mm_raw:.2f}, {y_bridge_mm_raw:.2f}) "
                f"final_mm=({x_bridge_mm_raw:.2f}, {y_bridge_mm_raw:.2f})"
            )

    return bridge_detections


class PieceStabilizer:
    def __init__(self, distance_threshold=50, alpha=0.7):
        self.prev_detections = []
        self.distance_threshold = float(distance_threshold)
        self.alpha = float(alpha)

    def stabilize(self, current_detections):
        stabilized = []
        for curr in current_detections:
            closest = None
            min_dist = float("inf")
            for prev in self.prev_detections:
                dist = np.sqrt(
                    (curr["centroid_px"][0] - prev["centroid_px"][0]) ** 2
                    + (curr["centroid_px"][1] - prev["centroid_px"][1]) ** 2
                )
                if dist < min_dist and dist < self.distance_threshold:
                    min_dist = dist
                    closest = prev

            if closest is not None:
                curr["centroid_px"][0] = self.alpha * curr["centroid_px"][0] + (1.0 - self.alpha) * closest["centroid_px"][0]
                curr["centroid_px"][1] = self.alpha * curr["centroid_px"][1] + (1.0 - self.alpha) * closest["centroid_px"][1]
                curr["rotation_deg"] = self.alpha * curr["rotation_deg"] + (1.0 - self.alpha) * closest["rotation_deg"]

            stabilized.append(curr)

        self.prev_detections = [dict(det) for det in stabilized]
        return stabilized
