"""Camera-only bridge detector test.

Usage: python bridge_camera_test.py

- Opens camera (configurable via `app_config` or defaults).
- Runs the bridge YOLO model and prints detections with robot XY (mm) and angle (deg).
- Press Q to quit.
"""

import time
from pathlib import Path
import json
import sys
import threading
import queue

import cv2
import numpy as np

# Try to load configuration from package; fallback to local defaults
try:
    from ModularProgramming import app_config
    CFG = app_config
except Exception:
    # minimal defaults
    class CFG:
        BRIDGE_MODEL_PATH = Path(__file__).resolve().parent.parent / 'model' / 'best_brigde.pt'
        CAMERA_INDEX = 0
        CAMERA_WIDTH = 1920
        CAMERA_HEIGHT = 1080
        CAMERA_FPS = 30
        CALIBRATION_JSON_PATH = Path(__file__).resolve().parent.parent / 'config' / 'camera_calibration.json'
        BRIDGE_CLASSES = ['small', 'large']
        BRIDGE_CONFIDENCE = 0.08

MODEL_PATH = Path(CFG.BRIDGE_MODEL_PATH)
CAL_JSON = Path(CFG.CALIBRATION_JSON_PATH) if hasattr(CFG, 'CALIBRATION_JSON_PATH') else Path(__file__).resolve().parent.parent / 'config' / 'camera_calibration.json'
BASE_HOMOG = Path(__file__).resolve().parent.parent / 'config' / 'homography.json'

# load camera calibration if present
camera_matrix = None
dist_coeffs = None
if CAL_JSON.exists():
    try:
        with open(CAL_JSON, 'r', encoding='utf-8') as f:
            cal = json.load(f)
        camera_matrix = np.array(cal['camera_matrix'], dtype=np.float64)
        dist_coeffs = np.array(cal['distortion_coefficients'], dtype=np.float64)
    except Exception:
        camera_matrix = None
        dist_coeffs = None

# load homography (base) and plus mapping if present
homography = None
if BASE_HOMOG.exists():
    try:
        with open(BASE_HOMOG, 'r', encoding='utf-8') as f:
            j = json.load(f)
        homography = np.array(j['homography_pixel_to_robot'], dtype=np.float64)
    except Exception:
        homography = None

plus = None

# helper: undistort pixel points using camera calibration
def undistort_pixels(pts):
    # pts: (N,2)
    if camera_matrix is None or dist_coeffs is None:
        return pts
    h, w = CFG.CAMERA_HEIGHT if hasattr(CFG,'CAMERA_HEIGHT') else 1080, CFG.CAMERA_WIDTH if hasattr(CFG,'CAMERA_WIDTH') else 1920
    newK, _ = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w,h), 0, (w,h))
    inp = pts.reshape(-1,1,2).astype(np.float64)
    und = cv2.undistortPoints(inp, camera_matrix, dist_coeffs, P=newK).reshape(-1,2)
    return und

# helper: apply homography
def map_to_robot(pts_und):
    # pts_und: (N,2)
    if homography is None:
        return np.zeros((pts_und.shape[0],2))
    pts = cv2.perspectiveTransform(pts_und.reshape(-1,1,2).astype(np.float32), homography.astype(np.float32)).reshape(-1,2)
    return pts

# load YOLO model if available
model = None
use_ultralytics = False
try:
    from ultralytics import YOLO
    if MODEL_PATH.exists():
        model = YOLO(str(MODEL_PATH))
        use_ultralytics = True
    else:
        print('Bridge model not found at', MODEL_PATH)
except Exception as e:
    print('Ultralytics not available or failed to load model:', e)

# Threaded detector: main thread shows frames; detector thread runs model on latest frame
frame_lock = threading.Lock()
latest_frame = None
latest_result = None
stop_event = threading.Event()

def detector_thread():
    global latest_frame, latest_result
    while not stop_event.is_set():
        frame = None
        with frame_lock:
            if latest_frame is not None:
                frame = latest_frame.copy()
                latest_frame = None
        if frame is None:
            time.sleep(0.005)
            continue
        if use_ultralytics and model is not None:
            try:
                res = model(frame, imgsz=640)[0]
                latest_result = res
            except Exception as e:
                print('Model run error:', e)
                latest_result = None
        else:
            latest_result = None
        time.sleep(0)

det_thread = threading.Thread(target=detector_thread, daemon=True)
det_thread.start()

# open camera
cap = cv2.VideoCapture(int(CFG.CAMERA_INDEX) if hasattr(CFG,'CAMERA_INDEX') else 0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(CFG.CAMERA_WIDTH) if hasattr(CFG,'CAMERA_WIDTH') else 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(CFG.CAMERA_HEIGHT) if hasattr(CFG,'CAMERA_HEIGHT') else 1080)

# create a resizable window and set to full HD
cv2.namedWindow('bridge_test_realtime', cv2.WINDOW_NORMAL)
try:
    cv2.resizeWindow('bridge_test_realtime', 1920, 1080)
except Exception:
    pass

print('Starting real-time camera. Press q to quit.')
fps_time = time.time()
frames = 0
fps = 0.0

while True:
    ret, frame = cap.read()
    if not ret:
        print('Camera read failed')
        break
    frames += 1
    # feed latest frame to detector thread (non-blocking)
    with frame_lock:
        latest_frame = frame.copy()

    # optionally undistort for display
    disp = frame.copy()
    if camera_matrix is not None:
        h,w = frame.shape[:2]
        newK, _ = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w,h), 0, (w,h))
        disp = cv2.undistort(frame, camera_matrix, dist_coeffs, None, newK)

    # draw latest results if available
    res = latest_result
    detections = []
    if res is not None:
        # try to extract boxes
        boxes = []
        try:
            xy = res.boxes.xyxy.cpu().numpy()
            clsv = res.boxes.cls.cpu().numpy()
            confv = res.boxes.conf.cpu().numpy()
            for (x1,y1,x2,y2), c, cf in zip(xy, clsv, confv):
                boxes.append({'xyxy':(float(x1),float(y1),float(x2),float(y2)), 'cls':int(c), 'conf':float(cf)})
        except Exception:
            # fallback older API
            if hasattr(res, 'boxes') and res.boxes is not None:
                for b in res.boxes:
                    try:
                        x1,y1,x2,y2 = map(float, b.xyxy[0])
                    except Exception:
                        try:
                            x1,y1,x2,y2 = float(b.xyxy[0][0]), float(b.xyxy[0][1]), float(b.xyxy[0][2]), float(b.xyxy[0][3])
                        except Exception:
                            continue
                    cls = int(b.cls[0]) if hasattr(b, 'cls') else int(b.cls)
                    conf = float(b.conf[0]) if hasattr(b, 'conf') else float(b.conf)
                    boxes.append({'xyxy':(x1,y1,x2,y2), 'cls':cls, 'conf':conf})
        names = None
        try:
            names = res.names
        except Exception:
            try:
                names = model.names
            except Exception:
                names = None
        for b in boxes:
            label = names[b['cls']] if names is not None and b['cls'] in names else str(b['cls'])
            if label in getattr(CFG, 'BRIDGE_CLASSES', ['small','large']):
                detections.append((b, label))

    for b,label in detections:
        x1,y1,x2,y2 = b['xyxy']
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        # map pixel -> robot
        px = np.array([[cx, cy]], dtype=np.float64)
        und = undistort_pixels(px)
        robot = map_to_robot(und)
        rx, ry = float(robot[0,0]), float(robot[0,1])

        # estimate angle using contours inside bbox
        bx1,by1,bx2,by2 = int(max(0,x1)), int(max(0,y1)), int(min(disp.shape[1]-1,x2)), int(min(disp.shape[0]-1,y2))
        roi = cv2.cvtColor(disp[by1:by2, bx1:bx2], cv2.COLOR_BGR2GRAY)
        angle_deg = 0.0
        try:
            _,th = cv2.threshold(roi,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                c = max(contours, key=cv2.contourArea)
                rect = cv2.minAreaRect(c)
                angle_deg = rect[2]
        except Exception:
            angle_deg = 0.0

        # pixel coordinates in camera
        pcx, pcy = int(round(cx)), int(round(cy))
        # draw bbox and annotations on the frame (no console printing)
        cv2.rectangle(disp, (bx1,by1), (bx2,by2), (0,255,0), 2)
        cv2.putText(disp, f'{label} {b["conf"]:.2f}', (bx1,by1-6), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
        cv2.putText(disp, f'px:({pcx},{pcy})', (bx1,by2+18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)
        cv2.putText(disp, f'robot:({rx:.1f},{ry:.1f})mm', (bx1,by2+36), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)
        cv2.putText(disp, f'angle:{angle_deg:.1f}deg', (bx1,by2+54), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,255), 1)

    # show FPS
    if frames % 10 == 0:
        now = time.time()
        fps = frames / (now - fps_time + 1e-6)
        frames = 0
        fps_time = now
    try:
        cv2.putText(disp, f'FPS: {fps:.1f}', (10,30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,255,0), 2)
    except Exception:
        pass

    # ensure display is full HD
    try:
        disp_show = cv2.resize(disp, (1920,1080))
    except Exception:
        disp_show = disp
    cv2.imshow('bridge_test_realtime', disp_show)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

stop_event.set()
det_thread.join(timeout=1.0)
cap.release()
cv2.destroyAllWindows()
