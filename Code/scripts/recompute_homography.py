"""Recompute homography matrix from image_points -> robot_points_mm in homography.json
Updates homography_pixel_to_robot, robot_predicted_mm entries, reprojection_errors, mean_error_mm and max_error_mm.
"""
import json
from pathlib import Path
import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
CFG = HERE.parent / "config" / "homography.json"

with open(CFG, 'r', encoding='utf-8') as f:
    data = json.load(f)

img_pts = np.array(data['image_points'], dtype=np.float64)
robot_pts = np.array(data['robot_points_mm'], dtype=np.float64)

if img_pts.shape[0] != robot_pts.shape[0] or img_pts.shape[0] < 4:
    raise SystemExit('Need same number of image_points and robot_points_mm (>=4)')

# compute homography using least squares (no RANSAC) to use all points
H, mask = cv2.findHomography(img_pts, robot_pts, method=0)
if H is None:
    raise SystemExit('findHomography failed')

# Predict robot points and compute reprojection errors
pred = []
errors = []
for (u,v), (xr, yr) in zip(img_pts, robot_pts):
    uv1 = np.array([u, v, 1.0], dtype=np.float64)
    x, y, w = H.dot(uv1)
    xp = float(x / w)
    yp = float(y / w)
    pred.append([xp, yp])
    err = float(np.hypot(xp - xr, yp - yr))
    errors.append(err)

mean_err = float(np.mean(errors))
max_err = float(np.max(errors))

# Update JSON structure
# homography matrix
data['homography_pixel_to_robot'] = [[float(H[r,c]) for c in range(3)] for r in range(3)]

# update reprojection_errors entries: robot_predicted_mm and error_mm, robot_expected_mm
if 'reprojection_errors' in data and isinstance(data['reprojection_errors'], list):
    re = data['reprojection_errors']
    # If lengths mismatch, rebuild entries
    if len(re) != len(img_pts):
        new_re = []
        for i, ((u,v), (xr,yr), (xp,yp), err) in enumerate(zip(img_pts.tolist(), robot_pts.tolist(), pred, errors), start=1):
            new_re.append({
                'point': f'P{i}',
                'pixel': [float(round(u,6)), float(round(v,6))],
                'robot_expected_mm': [float(round(xr,6)), float(round(yr,6))],
                'robot_predicted_mm': [float(round(xp,6)), float(round(yp,6))],
                'error_mm': float(round(err,6)),
                'inlier': True,
            })
        data['reprojection_errors'] = new_re
    else:
        for i, entry in enumerate(data['reprojection_errors']):
            xr, yr = robot_pts[i].tolist()
            xp, yp = pred[i]
            entry['robot_expected_mm'] = [float(round(xr,6)), float(round(yr,6))]
            entry['robot_predicted_mm'] = [float(round(xp,6)), float(round(yp,6))]
            entry['error_mm'] = float(round(errors[i],6))
            # mark as inlier if error < 50 mm (arbitrary)
            entry['inlier'] = errors[i] < 50.0

# update mean and max
data['mean_error_mm'] = float(round(mean_err,6))
data['max_error_mm'] = float(round(max_err,6))

# Save backup
bak = CFG.with_suffix('.json.bak')
with open(bak, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)

with open(CFG, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)

# Print summary
print('Recomputed homography:')
for row in data['homography_pixel_to_robot']:
    print('  ', ['{:.12f}'.format(v) for v in row])
print('\nPer-point reprojection errors (mm):')
for i, err in enumerate(errors, start=1):
    print(f' P{i}: {err:.6f} mm')
print(f'\nMean error: {mean_err:.6f} mm')
print(f'Max error: {max_err:.6f} mm')
print('\nUpdated file:', CFG)
