"""OpenCV overlays and console state printing.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import cv2
import numpy as np

from app_config import *
from app_utils import color_to_bgr, draw_text
from mediapipe_compat import mp

def draw_roi(output, roi, color, label=None, thickness=1):
    if roi is None:
        return
    x, y, w, h = [int(v) for v in roi]
    cv2.rectangle(output, (x, y), (x + w, y + h), color, thickness)
    if label:
        draw_text(output, label, x, max(15, y - 5), color, scale=0.6, thickness=2)


def draw_detections(output, detections):
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["xyxy"]]
        class_name = det["class_name"]
        conf = det["conf"]

        if class_name in BOX_CLASSES:
            color = (255, 0, 0)
        elif class_name in LID_CLASSES:
            color = (0, 255, 255)
        elif class_name in BATTERY_CLASSES:
            color = (0, 255, 0)
        elif class_name in TERMINAL_CLASSES:
            color = (255, 255, 255)
        else:
            color = (0, 0, 255)

        cv2.rectangle(output, (x1, y1), (x2, y2), color, 1)
        draw_text(output, f"{class_name} {conf:.2f}", x1, max(15, y1 - 4), color, scale=0.6, thickness=2)


def draw_station_state(output, results, rois_data):
    for rack_id, rack_data in rois_data.get("rack_slots", {}).items():
        roi_box = rack_data.get("roi_slot_box")
        roi_lid = rack_data.get("roi_lid")

        draw_roi(output, roi_box, (255, 0, 0), rack_id, 1)
        draw_roi(output, roi_lid, (0, 255, 255), "lid", 1)

        state = results.get(rack_id, {})
        if roi_box is not None:
            x, y, w, h = roi_box
            box_state = state.get("box_state", "unknown")
            lid_color = state.get("lid_color", None)
            open_color = state.get("open_box_color", None)

            if box_state == "closed":
                state_text = "CLOSED"
                detail_text = f"lid={lid_color}"
            elif box_state == "open":
                state_text = "OPEN"
                detail_text = f"box={open_color}"
            elif box_state == "empty":
                state_text = "EMPTY"
                detail_text = None
            else:
                state_text = "UNKNOWN"
                detail_text = None

            draw_text(output, f"{rack_id}: {state_text}", x, max(15, y - 47), (0, 255, 255), scale=0.6, thickness=2)
            if detail_text is not None:
                draw_text(output, detail_text, x, max(15, y - 25), (0, 255, 255), scale=0.6, thickness=2)

        for battery_id, battery_data in rack_data.get("battery_slots", {}).items():
            roi_battery = battery_data.get("roi_battery")
            roi_terminal = battery_data.get("roi_terminal_red")

            draw_roi(output, roi_battery, (0, 255, 0), battery_id.replace("battery_slot_", "B"), 1)
            draw_roi(output, roi_terminal, (255, 255, 255), "T", 1)

            b_state = state.get("battery_slots", {}).get(battery_id, {})
            if roi_battery is None:
                continue

            x, y, w, h = roi_battery
            present = b_state.get("battery_present", False)
            color = b_state.get("battery_color", None)
            polarity = b_state.get("polarity_ok", None)

            if not present:
                text_parts = [("empty", (160, 160, 160), False)]
            else:
                if polarity is True:
                    text_parts = [(f"{color} ", (0, 255, 0), False), ("OK", (0, 255, 0), False)]
                elif polarity is False:
                    text_parts = [(f"{color} ", (0, 255, 0), False), ("BAD", (0, 0, 255), True)]
                else:
                    text_parts = [(f"{color} ", (0, 255, 0), False), ("?", (0, 255, 0), False)]

            part_sizes = [
                cv2.getTextSize(part_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                for part_text, _, _ in text_parts
            ]
            text_w = sum(part_w for part_w, _ in part_sizes)
            text_h = max(part_h for _, part_h in part_sizes)
            text_x = x + max(0, (w - text_w) // 2)
            text_y = y + (h + text_h) // 2
            for (part_text, part_color, has_shadow), (part_w, _) in zip(text_parts, part_sizes):
                if has_shadow:
                    draw_text(output, part_text, text_x + 1, text_y + 1, (0, 0, 0), scale=0.5, thickness=4)
                draw_text(output, part_text, text_x, text_y, part_color, scale=0.5, thickness=2)
                text_x += part_w


def draw_bridge_state(output, bridge_state, bridge_detections):
    if output is None:
        return

    for det in bridge_detections or []:
        if det.get("inside_homography") is False:
            continue

        piece_type = det.get("class_name")
        if piece_type not in BRIDGE_CLASSES:
            continue

        cx, cy = det["centroid_px"]
        angle_deg = det["rotation_deg"]
        x_robot, y_robot = det["center_bridge_mm"]

        color = (0, 200, 255) if piece_type == "small" else (255, 160, 0)

        contour = det.get("contour")
        if contour:
            pts = np.array(contour, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(output, [pts], isClosed=True, color=color, thickness=2)
        else:
            x1, y1, x2, y2 = [int(v) for v in det.get("xyxy", [cx, cy, cx, cy])]
            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)

        center = (int(cx), int(cy))
        cv2.circle(output, center, 6, color, -1)
        cv2.circle(output, center, 12, color, 2)

        angle_rad = np.deg2rad(float(angle_deg))
        axis_len = 55
        end_x = int(cx + axis_len * np.cos(angle_rad))
        end_y = int(cy + axis_len * np.sin(angle_rad))
        cv2.line(output, center, (end_x, end_y), color, 3)

        text_x = int(cx) + 14
        text_y = int(cy) - 20
        draw_text(output, f"cords = ({x_robot:.1f}, {y_robot:.1f})", text_x, text_y, (0, 0, 0), scale=0.6, thickness=4)
        draw_text(output, f"angle = {angle_deg:.1f}", text_x, text_y + 24, (0, 0, 0), scale=0.6, thickness=4)
        draw_text(output, f"cords = ({x_robot:.1f}, {y_robot:.1f})", text_x, text_y, color, scale=0.6, thickness=2)
        draw_text(output, f"angle = {angle_deg:.1f}", text_x, text_y + 24, color, scale=0.6, thickness=2)


def draw_robot_overlay(output, robot_state, robot_detections):
    return


def draw_hand_overlay(output, hand_state):
    if output is None or hand_state is None:
        return

    hand_landmarks_px = hand_state.get("hand_landmarks_px")
    if not hand_landmarks_px:
        return

    if hand_state.get("hand_on_red"):
        color = (0, 0, 255)
        label = "HAND RED"
    elif hand_state.get("hand_on_green"):
        color = (0, 255, 0)
        label = "HAND GREEN"
    else:
        color = (0, 255, 255)
        label = "HAND"

    confidence = float(hand_state.get("hand_confidence", 0.0) or 0.0)

    # Mostrar/dibujar la mano solo si la confianza supera el umbral de seguridad
    if confidence < HAND_SAFETY_CONFIDENCE_THRESHOLD:
        return

    label = f"MANO DETECTADA {confidence:.2f}"

    if mp is not None and hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
        for connection in mp.solutions.hands.HAND_CONNECTIONS:
            start_idx, end_idx = connection
            if start_idx < len(hand_landmarks_px) and end_idx < len(hand_landmarks_px):
                p1 = tuple(int(v) for v in hand_landmarks_px[start_idx])
                p2 = tuple(int(v) for v in hand_landmarks_px[end_idx])
                cv2.line(output, p1, p2, color, 2)

    for px, py in hand_landmarks_px:
        cv2.circle(output, (int(px), int(py)), 4, color, -1)

    hand_center = hand_state.get("hand_center")
    if hand_center is not None:
        cx, cy = hand_center
        draw_text(output, label, cx + 10, max(15, cy - 10), color, scale=0.5, thickness=2)


def print_station_state(results):
    print("\n========== STATION STATE ==========")
    for rack_id, rack_state in results.items():
        print(f"\n{rack_id}:")
        print(f"  box_present: {rack_state['box_present']}")
        print(f"  box_state: {rack_state['box_state']}")
        print(f"  confirmed_open: {rack_state['confirmed_open']}")
        print(f"  lid_color: {rack_state['lid_color']}")
        print(f"  open_box_color: {rack_state['open_box_color']}")
        for battery_id, battery_state in rack_state["battery_slots"].items():
            print(
                f"  {battery_id}: "
                f"present={battery_state['battery_present']}, "
                f"color={battery_state['battery_color']}, "
                f"polarity_ok={battery_state['polarity_ok']}"
            )
    print("===================================")
