import json
from pathlib import Path
import numpy as np
import cv2

BASE = Path(__file__).resolve().parent.parent
CFG = BASE / 'config' / 'homography.json'
CAL = BASE / 'config' / 'camera_calibration.json'

IMG = Path.home() / 'Desktop' / 'Homografía.jpg'
OUT = Path.home() / 'Desktop' / 'overlay_calibration_desktop.png'

with open(CFG,'r',encoding='utf-8') as f:
    data = json.load(f)
with open(CAL,'r',encoding='utf-8') as f:
    cal = json.load(f)

img_pts = np.array(data['image_points'], dtype=np.float64)
H = np.array(data['homography_pixel_to_robot'], dtype=np.float64)

camera_matrix = np.array(cal['camera_matrix'], dtype=np.float64)
dist_coeffs = np.array(cal['distortion_coefficients'], dtype=np.float64)

img = cv2.imread(str(IMG))
if img is None:
    try:
        from PIL import Image
        pil = Image.open(str(IMG)).convert('RGB')
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise SystemExit(f'Image not found or unreadable: {IMG} -- {e}')

h,w = img.shape[:2]
new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w,h), 0, (w,h))
undistorted_img = cv2.undistort(img, camera_matrix, dist_coeffs, None, new_camera_matrix)

pts = img_pts.reshape(-1,1,2).astype(np.float64)
undistorted = cv2.undistortPoints(pts, camera_matrix, dist_coeffs, P=new_camera_matrix)
transformed = cv2.perspectiveTransform(undistorted, H.astype(np.float32))

out = undistorted_img.copy()
for i,(und, rob) in enumerate(zip(undistorted.reshape(-1,2), transformed.reshape(-1,2)), start=1):
    ux,uy = int(round(und[0])), int(round(und[1]))
    rx,ry = float(rob[0]), float(rob[1])
    cv2.circle(out, (ux,uy), 8, (0,255,0), -1)
    cv2.putText(out, f'P{i}', (ux+10, uy-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
    cv2.putText(out, f'({rx:.1f},{ry:.1f})mm', (ux+10, uy+18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)

cv2.imwrite(str(OUT), out)
print('Wrote overlay to', OUT)
