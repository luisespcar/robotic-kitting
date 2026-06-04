"""Generic IO and drawing helpers shared by the vision app.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2

def load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_image_unicode(output_path, image):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(output_path.suffix.lower(), image)
    if not success:
        return False
    encoded.tofile(str(output_path))
    return True


def draw_text(img, text, x, y, color, scale=0.6, thickness=2):
    cv2.putText(
        img,
        str(text),
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def color_to_bgr(color_name):
    if color_name == "red":
        return (0, 0, 255)
    if color_name == "green":
        return (0, 255, 0)
    if color_name == "blue":
        return (255, 0, 0)
    return (180, 180, 180)
