# Development of a Robotic Kitting System for Battery Cells Using AI-Based Computer Vision and Digital Twin Technology

[![Python](https://img.shields.io/badge/Python-3.13.12-blue?logo=python)](https://www.python.org/)
![YOLOv8](https://img.shields.io/badge/YOLOv8%20-%20?style=flat&logo=YOLO&label=Ultralytics&labelColor=grey&link=https%3A%2F%2Fdocs.ultralytics.com%2F
)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green?logo=opencv)](https://opencv.org/)
[![RoboDK](https://img.shields.io/badge/RoboDK-Digital_Twin-darkgreen)](https://robodk.com/)
[![UR10e](https://img.shields.io/badge/UR10e-Collaborative_Robot-orange)](https://www.universal-robots.com/products/ur10-robot/)
[![Robotiq](https://img.shields.io/badge/Gripper-Robotiq_2F--85-color=%23ffdcb2)](https://robotiq.com/products/2f85-140-adaptive-robot-gripper)
[![License](https://img.shields.io/badge/License-MIT-yellow)](https://opensource.org/licenses/MIT)

## Overview

This repository contains the implementation developed for the Bachelor's Degree Project:

**"Development of a Robotic Kitting System for Battery Cells Using AI-Based Computer Vision and Digital Twin Technology"**

The project presents a complete robotic kitting solution capable of detecting, classifying, sorting, and assembling battery-cell kits using:

* Universal Robots UR10e collaborative robot
* AI-based Computer Vision (YOLOv8)
* OpenCV image processing
* RoboDK Digital Twin
* Camera calibration and pixel-to-robot mapping

The system was developed following Industry 5.0 principles, combining collaborative robotics, artificial intelligence, and digital twins to create a flexible and safe manufacturing workstation.

---

## 🎥 System Demonstration

[![UR10e Battery Cell Kitting System](https://img.youtube.com/vi/CinmK6UtbHQ/maxresdefault.jpg)](https://www.youtube.com/watch?v=CinmK6UtbHQ)

*Click the image to watch the complete demonstration video.*

## ✨ Main Features

- 🤖 Vision-guided robotic kitting with UR10e
- 🔍 Real-time battery cell detection using YOLOv8
- 🎯 Automatic polarity and orientation verification
- 📍 Camera calibration and image-to-world mapping
- 📦 Automated pick-and-place and sorting operations
- 🏭 Real-time RoboDK Digital Twin synchronization
- 🚧 Collision-aware trajectory validation
- ✋ Human-safe collaborative robotics workflow
- ⚡ Low-latency communication architecture
- 🔄 Support for both Classical CV and AI-based detection

---

## System Architecture

The system is divided into three main layers:

```text
┌─────────────────────────────┐
│      Vision Layer           │
│ OpenCV + YOLOv8 + Camera    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      Computing Layer        │
│ Detection & Decision Logic  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      Digital Twin Layer     │
│          RoboDK             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      Robot Layer            │
│ UR10e + Robotiq 2F-85       │
└─────────────────────────────┘
```

---

## Hardware

### Robot

* Universal Robots UR10e
* 6 DOF Collaborative Robot
* Reach: 1300 mm
* Payload: 12.5 kg

### Gripper

* Robotiq 2F-85 Adaptive Gripper

### Vision System

* Logitech C922 Pro HD Camera
* 1080p RGB acquisition

### Additional Equipment

* 3D printed custom fixtures
* Battery-cell kitting workstation
* Industrial PC with GPU acceleration

---

## Software Stack

### Programming

* Python 3.x

### Computer Vision

* OpenCV
* NumPy
* Ultralytics YOLOv8

### AI Training

* Roboflow
* YOLOv8 Detection
* YOLOv8 Segmentation

### Robotics

* RoboDK API
* URScript
* Universal Robots PolyScope

### Development Tools

* Visual Studio Code

---

## Computer Vision Approach

### YOLOv8 + ROI Detection

Deep Learning approach based on:

* YOLOv8 object detection
* YOLOv8 segmentation
* Camera calibration
* Homography transformation
* Pose estimation

Advantages:

* Higher robustness
* Better generalization
* Improved detection reliability

---

## Main Features

### Battery Detection

* Battery presence verification
* Battery type identification
* Polarity detection

### Component Detection

* Battery cells
* Lids
* Bridge pieces
* Kit boxes

### Pose Estimation

* Object centroid extraction
* Orientation angle calculation
* Pixel-to-robot coordinate conversion

### Robot Operations

* Pick-and-place
* Sorting
* Assembly
* Error handling

### Digital Twin

* Real-time synchronization
* Collision detection
* Trajectory validation
* Robot monitoring

---

## Safety Features

The system incorporates several safety mechanisms:

* Hand absence verification
* Collision avoidance
* Speed limitation
* Digital twin validation
* Safe battery handling procedures

---

## Repository Structure

```text
project/
│
├── dataset/
│   ├── images/
│   ├── labels/
│   └── data.yaml
│
├── vision/
│   ├── roi_detection/
│   ├── yolo_detection/
│   ├── segmentation/
│   └── calibration/
│
├── robodk/
│   ├── stations/
│   ├── programs/
│   └── api/
│
├── robot/
│   ├── urscript/
│   └── communication/
│
├── models/
│   ├── yolo_detection.pt
│   └── yolo_segmentation.pt
│
├── assets/
│   ├── images/
│   ├── videos/
│   └── diagrams/
│
├── docs/
│   └── thesis.pdf
│
└── README.md
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/your-username/battery-cell-kitting-system.git

cd battery-cell-kitting-system
```

Create a virtual environment:

```bash
python -m venv venv

source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Running the Vision System

```bash
python vision/yolo_detection/main.py
```

---

## Running the Digital Twin

1. Open RoboDK.
2. Load the station file.
3. Connect to the UR10e robot.
4. Start the Python communication script.
5. Execute the kitting process.

---

## Authors

**Adrián Ortiz Murillo**

**Luis España Carnero**

Bachelor Degree Project

University of Skövde

ASSAR Industrial Innovation Arena

Spring 2026

---

## License

This repository is intended for academic and research purposes.

Please cite the corresponding thesis if you use this work in your research or development projects.
