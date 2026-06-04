import cv2
import json
import numpy as np
from pathlib import Path


# ---------------- CONFIGURATION ----------------

IMAGE_PATH = Path.home() / "Desktop" / "Homografía.jpg"

if not IMAGE_PATH.exists():
    # fallback common extensions
    for ext in (".jpg", ".jpeg", ".png", ".bmp"):
        p = Path.home() / "Desktop" / ("Homografía" + ext)
        if p.exists():
            IMAGE_PATH = p
            break

CALIBRATION_JSON_PATH = Path(r"C:\Users\luise\OneDrive - Högskolan i Skövde\TFG\Code nueva homografia\ModularProgramming\config\camera_calibration.json")

OUTPUT_JSON_PATH = Path(r"C:\Users\luise\OneDrive - Högskolan i Skövde\TFG\Code nueva homografia\ModularProgramming\config\homography.json")

OUTPUT_DEBUG_IMAGE_PATH = Path.home() / "Desktop" / "homography_debug_points.jpg"

USE_CAMERA_CALIBRATION = True
UNDISTORT_ALPHA = 1.0  # 0.0 = crop, 1.0 = keep all pixels (may add black regions)

# Mínimo 4 puntos. Recomendado 6 u 8.
NUM_POINTS = 8

# Alturas del plano. Ajusta después según tu robot.
Z_PICK_MM = 45.0
Z_APPROACH_MM = 120.0

WINDOW_NAME = "Plane Homography Calibration"

WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

# ------------------------------------------------


class AppState:
    def __init__(self):
        self.original_image = None
        self.image = None
        self.display = None

        self.image_points = []
        self.robot_points = []

        self.mode = "collect"  # collect / test

        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0

        self.panning = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self.H = None


state = AppState()


# ---------------- FILE HELPERS ----------------

def read_image_unicode(path):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise RuntimeError(f"Could not read image: {path}")

    return image


def load_json(path):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"JSON not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def save_image_unicode(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ok, encoded = cv2.imencode(path.suffix.lower(), image)

    if not ok:
        raise RuntimeError(f"Could not encode image: {path}")

    encoded.tofile(str(path))


# ---------------- CAMERA CALIBRATION ----------------

def load_camera_calibration(json_path):
    calibration = load_json(json_path)

    camera_matrix = np.array(
        calibration["camera_matrix"],
        dtype=np.float64
    )

    dist_coeffs = np.array(
        calibration["distortion_coefficients"],
        dtype=np.float64
    )

    return camera_matrix, dist_coeffs


def undistort_image(image, calibration_json_path):
    camera_matrix, dist_coeffs = load_camera_calibration(calibration_json_path)

    h, w = image.shape[:2]

    new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
        camera_matrix,
        dist_coeffs,
        (w, h),
        UNDISTORT_ALPHA,
        (w, h)
    )

    undistorted = cv2.undistort(
        image,
        camera_matrix,
        dist_coeffs,
        None,
        new_camera_matrix
    )

    return undistorted


# ---------------- COORDINATES ----------------

def center_view():
    h, w = state.image.shape[:2]

    scale_w = WINDOW_WIDTH / w
    scale_h = WINDOW_HEIGHT / h

    state.zoom = min(scale_w, scale_h, 1.0)
    state.pan_x = int((WINDOW_WIDTH - w * state.zoom) / 2)
    state.pan_y = int((WINDOW_HEIGHT - h * state.zoom) / 2)


def image_to_display_point(x, y):
    dx = int(x * state.zoom + state.pan_x)
    dy = int(y * state.zoom + state.pan_y)

    return dx, dy


def display_to_image_point(dx, dy):
    x = int((dx - state.pan_x) / state.zoom)
    y = int((dy - state.pan_y) / state.zoom)

    h, w = state.image.shape[:2]

    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))

    return x, y


# ---------------- HOMOGRAPHY ----------------

def compute_homography():
    if len(state.image_points) < 4:
        raise RuntimeError("Need at least 4 points to compute homography.")

    image_points = np.array(state.image_points, dtype=np.float64)
    robot_points = np.array(state.robot_points, dtype=np.float64)

    # Use RANSAC to reduce influence of outliers. The reprojection threshold
    # is in destination units (robot mm), choose a reasonable default (5 mm).
    ransac_thresh = 5.0
    H, status = cv2.findHomography(
        image_points,
        robot_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=ransac_thresh
    )

    if H is None:
        raise RuntimeError("Could not compute homography.")

    state.H = H

    return H, status


def pixel_to_robot(u, v, H):
    point = np.array([[[float(u), float(v)]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(point, H)

    x_robot, y_robot = transformed[0][0]

    return float(x_robot), float(y_robot)


def compute_reprojection_errors(H):
    errors = []
    for i, (img_pt, robot_pt) in enumerate(zip(state.image_points, state.robot_points), start=1):
        u, v = img_pt
        expected_x, expected_y = robot_pt

        pred_x, pred_y = pixel_to_robot(u, v, H)

        error = np.sqrt(
            (pred_x - expected_x) ** 2 +
            (pred_y - expected_y) ** 2
        )

        errors.append({
            "point": f"P{i}",
            "pixel": [float(u), float(v)],
            "robot_expected_mm": [float(expected_x), float(expected_y)],
            "robot_predicted_mm": [float(pred_x), float(pred_y)],
            "error_mm": float(error),
            "inlier": True,
        })

    # If RANSAC was used, try to mark outliers using the current state.H if available
    if state.H is not None:
        # Re-evaluate inliers by checking reprojection distances
        for e in errors:
            u, v = e["pixel"]
            pred_x, pred_y = pixel_to_robot(u, v, state.H)
            e["robot_predicted_mm"] = [pred_x, pred_y]
            e["error_mm"] = float(np.sqrt((pred_x - e["robot_expected_mm"][0]) ** 2 + (pred_y - e["robot_expected_mm"][1]) ** 2))
            # Mark as outlier if error exceeds a threshold
            e["inlier"] = e["error_mm"] <= 5.0

    return errors


# ---------------- DRAW ----------------

def get_display_image():
    image = state.image

    h, w = image.shape[:2]

    scaled_w = max(1, int(w * state.zoom))
    scaled_h = max(1, int(h * state.zoom))

    resized = cv2.resize(
        image,
        (scaled_w, scaled_h),
        interpolation=cv2.INTER_AREA
    )

    canvas = np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH, 3), dtype=np.uint8)

    x0 = int(state.pan_x)
    y0 = int(state.pan_y)
    x1 = x0 + scaled_w
    y1 = y0 + scaled_h

    canvas_x0 = max(0, x0)
    canvas_y0 = max(0, y0)
    canvas_x1 = min(WINDOW_WIDTH, x1)
    canvas_y1 = min(WINDOW_HEIGHT, y1)

    img_x0 = max(0, -x0)
    img_y0 = max(0, -y0)
    img_x1 = img_x0 + (canvas_x1 - canvas_x0)
    img_y1 = img_y0 + (canvas_y1 - canvas_y0)

    if canvas_x1 > canvas_x0 and canvas_y1 > canvas_y0:
        canvas[canvas_y0:canvas_y1, canvas_x0:canvas_x1] = resized[
            img_y0:img_y1,
            img_x0:img_x1
        ]

    return canvas


def draw_label(img, text, x, y, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1

    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)

    x = int(x)
    y = int(max(25, y))

    cv2.rectangle(
        img,
        (x, y - th - baseline - 5),
        (x + tw + 8, y + baseline + 5),
        (0, 0, 0),
        -1
    )

    cv2.putText(
        img,
        text,
        (x + 4, y),
        font,
        scale,
        color,
        thickness,
        cv2.LINE_AA
    )


def draw_cross(img, x, y, color, size=8, thickness=2):
    x = int(x)
    y = int(y)

    cv2.line(img, (x - size, y), (x + size, y), color, thickness)
    cv2.line(img, (x, y - size), (x, y + size), color, thickness)
    cv2.circle(img, (x, y), size + 3, color, thickness)


def draw_overlay():
    output = get_display_image()

    # Puntos ya clicados
    for i, (u, v) in enumerate(state.image_points, start=1):
        dx, dy = image_to_display_point(u, v)

        draw_cross(output, dx, dy, (0, 255, 0), size=8, thickness=2)

        label = f"P{i}"

        if i <= len(state.robot_points):
            rx, ry = state.robot_points[i - 1]
            label += f" -> X={rx:.1f}, Y={ry:.1f}"

        draw_label(
            output,
            label,
            dx + 10,
            dy - 10,
            (0, 255, 0)
        )

    # Panel superior
    cv2.rectangle(output, (0, 0), (WINDOW_WIDTH, 120), (0, 0, 0), -1)

    if state.mode == "collect":
        mode_text = f"COLLECT POINTS: click P{len(state.image_points) + 1}/{NUM_POINTS}"
    else:
        mode_text = "TEST MODE: click any point to get robot coordinates"

    cv2.putText(
        output,
        mode_text,
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.putText(
        output,
        f"Points: {len(state.image_points)}/{NUM_POINTS} | Zoom: {state.zoom:.2f}",
        (20, 72),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    cv2.putText(
        output,
        "Left click: select/test point | Wheel: zoom | Right drag: pan | C center | U undo | G save | Q quit",
        (20, 108),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1
    )

    return output


def create_debug_image(H=None):
    debug = state.image.copy()

    for i, (u, v) in enumerate(state.image_points, start=1):
        draw_cross(debug, u, v, (0, 255, 0), size=10, thickness=2)

        text = f"P{i}"

        if i <= len(state.robot_points):
            rx, ry = state.robot_points[i - 1]
            text += f" X={rx:.1f} Y={ry:.1f}"

        cv2.putText(
            debug,
            text,
            (int(u) + 12, int(v) - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
            cv2.LINE_AA
        )

    return debug


# ---------------- INPUT ----------------

def ask_robot_coordinates(point_index):
    print()
    print(f"Introduce coordenadas robot para P{point_index}.")
    print("Formato recomendado: X Y")
    print("Ejemplo: 450.0 -250.0")
    print()

    while True:
        raw = input(f"P{point_index} robot X Y mm: ").strip()
        raw = raw.replace(",", " ")

        parts = raw.split()

        if len(parts) != 2:
            print("Formato incorrecto. Escribe dos números: X Y")
            continue

        try:
            x_robot = float(parts[0])
            y_robot = float(parts[1])
            return [x_robot, y_robot]
        except ValueError:
            print("No he podido convertir X,Y a número.")


def save_homography_json():
    H, status = compute_homography()
    # status is a mask from RANSAC (if used)
    errors = compute_reprojection_errors(H)

    inlier_count = None
    try:
        if status is not None:
            inlier_count = int(np.sum(status))
    except Exception:
        inlier_count = None

    mean_error = float(np.mean([e["error_mm"] for e in errors]))
    max_error = float(np.max([e["error_mm"] for e in errors]))

    output = {
        "description": "Homography from corrected image pixels to robot XY coordinates",
        "important": "Use this homography only with undistorted images from the same camera pose.",
        "source_image": str(IMAGE_PATH).replace("\\", "/"),
        "used_camera_calibration": bool(USE_CAMERA_CALIBRATION),
        "calibration_json": str(CALIBRATION_JSON_PATH).replace("\\", "/") if USE_CAMERA_CALIBRATION else None,
        "coordinate_format": {
            "image_points": "[u_px, v_px]",
            "robot_points_mm": "[x_mm, y_mm]"
        },
        "image_points": [
            [float(u), float(v)]
            for u, v in state.image_points
        ],
        "robot_points_mm": [
            [float(x), float(y)]
            for x, y in state.robot_points
        ],
        "homography_pixel_to_robot": H.tolist(),
        "z_pick_mm": float(Z_PICK_MM),
        "z_approach_mm": float(Z_APPROACH_MM),
        "reprojection_errors": errors,
        "inlier_count": inlier_count,
        "mean_error_mm": mean_error,
        "max_error_mm": max_error,
    }

    save_json(output, OUTPUT_JSON_PATH)

    debug_image = create_debug_image(H)
    save_image_unicode(OUTPUT_DEBUG_IMAGE_PATH, debug_image)

    print()
    print("===== HOMOGRAPHY SAVED =====")
    print(f"JSON: {OUTPUT_JSON_PATH}")
    print(f"Debug image: {OUTPUT_DEBUG_IMAGE_PATH}")
    print(f"Mean error: {mean_error:.3f} mm")
    print(f"Max error: {max_error:.3f} mm")
    print("============================")
    print()

    state.mode = "test"


# ---------------- MOUSE ----------------

def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        u, v = display_to_image_point(x, y)

        if state.mode == "collect":
            if len(state.image_points) >= NUM_POINTS:
                print("All points already collected. Press G to save or U to undo.")
                return

            point_index = len(state.image_points) + 1

            print()
            print(f"[CLICK] P{point_index}: pixel u={u}, v={v}")

            robot_xy = ask_robot_coordinates(point_index)

            state.image_points.append([float(u), float(v)])
            state.robot_points.append(robot_xy)

            print(f"[SAVED POINT] P{point_index}: pixel={[u, v]} -> robot={robot_xy}")

            if len(state.image_points) == NUM_POINTS:
                print()
                print("All points collected.")
                print("Press G to compute and save homography.")
                print()

        elif state.mode == "test":
            if state.H is None:
                try:
                    compute_homography()
                except Exception as exc:
                    print(f"Could not compute homography: {exc}")
                    return

            x_robot, y_robot = pixel_to_robot(u, v, state.H)

            print()
            print(f"[TEST CLICK] pixel=({u}, {v}) -> robot X={x_robot:.2f} mm, Y={y_robot:.2f} mm")

    elif event == cv2.EVENT_RBUTTONDOWN:
        state.panning = True
        state.last_mouse_x = x
        state.last_mouse_y = y

    elif event == cv2.EVENT_MOUSEMOVE:
        if state.panning:
            dx = x - state.last_mouse_x
            dy = y - state.last_mouse_y

            state.pan_x += dx
            state.pan_y += dy

            state.last_mouse_x = x
            state.last_mouse_y = y

    elif event == cv2.EVENT_RBUTTONUP:
        state.panning = False

    elif event == cv2.EVENT_MOUSEWHEEL:
        img_x_before, img_y_before = display_to_image_point(x, y)

        if flags > 0:
            state.zoom *= 1.15
        else:
            state.zoom /= 1.15

        state.zoom = max(0.2, min(10.0, state.zoom))

        state.pan_x = int(x - img_x_before * state.zoom)
        state.pan_y = int(y - img_y_before * state.zoom)


# ---------------- MAIN ----------------

def main():
    print("Loading image...")
    state.original_image = read_image_unicode(IMAGE_PATH)

    if USE_CAMERA_CALIBRATION:
        print("Undistorting image...")
        state.image = undistort_image(
            state.original_image,
            CALIBRATION_JSON_PATH
        )
    else:
        state.image = state.original_image.copy()

    center_view()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_WIDTH, WINDOW_HEIGHT)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    print()
    print("Plane homography calibration started.")
    print()
    print("Instructions:")
    print("  1. Click each physical mark in the image.")
    print("  2. After each click, type the robot coordinates X Y in mm.")
    print("  3. When all points are collected, press G to save.")
    print("  4. After saving, click anywhere to test pixel -> robot conversion.")
    print()
    print("Controls:")
    print("  Left click  -> collect/test point")
    print("  Right drag  -> pan")
    print("  Mouse wheel -> zoom")
    print("  C           -> center view")
    print("  U           -> undo last point")
    print("  G           -> compute/save homography")
    print("  Q / ESC     -> quit")
    print()

    while True:
        display = draw_overlay()
        cv2.imshow(WINDOW_NAME, display)

        key = cv2.waitKeyEx(20)

        if key == -1:
            continue

        if key in [ord("q"), ord("Q"), 27]:
            print("Exiting.")
            break

        elif key in [ord("c"), ord("C")]:
            center_view()
            print("View centered.")

        elif key in [ord("u"), ord("U")]:
            if state.image_points:
                removed_img = state.image_points.pop()
                removed_robot = state.robot_points.pop()
                state.H = None
                state.mode = "collect"
                print(f"Removed last point: pixel={removed_img}, robot={removed_robot}")
            else:
                print("No points to undo.")

        elif key in [ord("g"), ord("G")]:
            if len(state.image_points) < 4:
                print("Need at least 4 points to save homography.")
                continue

            try:
                save_homography_json()
            except Exception as exc:
                print(f"[ERROR] Could not save homography: {exc}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()