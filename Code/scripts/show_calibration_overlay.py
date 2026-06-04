import json
from pathlib import Path
import numpy as np
import cv2

BASE = Path(__file__).resolve().parent.parent
CFG = BASE / 'config' / 'homography.json'
CAL = BASE / 'config' / 'camera_calibration.json'
# candidate images (pick the first that exists)
IMG_CANDIDATES = [
    BASE / 'tests' / 'captura_vision_logic_003930.png',
    BASE.parent / 'Code' / 'tests' / 'captura_vision_logic_003930.png',
    BASE.parent / 'VisionLogicV1' / 'tests' / 'captura_vision_logic_003930.png',
    BASE.parent / 'Camera' / 'RobotCogeTapa.jpeg',
]
# also try from the workspace root (two levels up)
root = BASE.parent.parent
IMG_CANDIDATES.extend([
    root / 'Code' / 'tests' / 'captura_vision_logic_003930.png',
    root / 'VisionLogicV1' / 'tests' / 'captura_vision_logic_003930.png',
    root / 'Camera' / 'RobotCogeTapa.jpeg',
    root / 'imagenes' / 'UR10e.png',
])
# also try the user's Desktop (common location for ad-hoc images)
from pathlib import Path as _P
IMG_CANDIDATES.insert(0, _P.home() / 'Desktop' / 'Homografía.jpg')
IMG = None
for p in IMG_CANDIDATES:
    if p.exists():
        IMG = p
        break
if IMG is None:
    raise SystemExit(f'No candidate image found; tried: {IMG_CANDIDATES}')

OUT = BASE / 'tests' / 'overlay_calibration.png'

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
    # fallback: use PIL to handle non-ascii paths/filenames reliably
    try:
        from PIL import Image
        pil = Image.open(str(IMG)).convert('RGB')
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        raise SystemExit(f'Image not found or unreadable by cv2/PIL: {IMG}')
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
    # draw circle and label
    cv2.circle(out, (ux,uy), 8, (0,255,0), -1)
    cv2.putText(out, f'P{i}', (ux+10, uy-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
    cv2.putText(out, f'({rx:.1f},{ry:.1f})mm', (ux+10, uy+18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)

cv2.imwrite(str(OUT), out)
print('Overlay image written to', OUT)
