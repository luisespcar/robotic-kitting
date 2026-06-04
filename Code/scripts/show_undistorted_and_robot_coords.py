import json
from pathlib import Path
import numpy as np
import cv2

BASE = Path(__file__).resolve().parent.parent
CFG = BASE / 'config' / 'homography.json'
CAL = BASE / 'config' / 'camera_calibration.json'

with open(CFG,'r',encoding='utf-8') as f:
    data = json.load(f)
with open(CAL,'r',encoding='utf-8') as f:
    cal = json.load(f)

img_pts = np.array(data['image_points'], dtype=np.float64)
H = np.array(data['homography_pixel_to_robot'], dtype=np.float64)

camera_matrix = np.array(cal['camera_matrix'], dtype=np.float64)
dist_coeffs = np.array(cal['distortion_coefficients'], dtype=np.float64)

h,w = 1080,1920
new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w,h), 0, (w,h))

# undistortPoints expects shape (N,1,2) for input
pts = img_pts.reshape(-1,1,2).astype(np.float64)
undistorted = cv2.undistortPoints(pts, camera_matrix, dist_coeffs, P=new_camera_matrix)
# undistorted are in pixel coordinates with P

# apply homography to undistorted
transformed = cv2.perspectiveTransform(undistorted, H.astype(np.float32))

print('idx, original_px -> undistorted_px -> robot_mm')
for i,(orig, und, rob) in enumerate(zip(img_pts, undistorted.reshape(-1,2), transformed.reshape(-1,2)), start=1):
    ox,oy = float(orig[0]), float(orig[1])
    ux,uy = float(und[0]), float(und[1])
    rx,ry = float(rob[0]), float(rob[1])
    print(f'P{i}: ({ox:.3f},{oy:.3f}) -> ({ux:.3f},{uy:.3f}) -> ({rx:.3f} mm, {ry:.3f} mm)')
