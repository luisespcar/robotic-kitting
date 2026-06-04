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

* Python 3.13.12

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
ModularProgramming/
│
├── config/
│   ├── camera_calibration.json
│   ├── homography.json
│   └── yolo_logic_rois_updated.json
│
├── model/
│   ├── best.pt
│   ├── best_brigde.pt
│   ├── best_robot.pt
│   └── hand_landmarker.task
│
├── scripts/
│   ├── bridge_camera_test.py
│   ├── recompute_homography.py
│   ├── show_calibration_overlay.py
│   ├── show_calibration_overlay_to_desktop.py
│   └── show_undistorted_and_robot_coords.py
│
├── station_mixins/
│   ├── bridge_mixin.py
│   ├── cell_motion_mixin.py
│   ├── cell_processing_mixin.py
│   ├── completion_mixin.py
│   ├── evaluation_mixin.py
│   ├── lid_flow_mixin.py
│   ├── memory_mixin.py
│   ├── robodk_motion_mixin.py
│   ├── safety_mixin.py
│   └── __init__.py
│
├── tests/
│   ├── calibrate_plane_homography (1).py
│   ├── calibrate_plane_homography (2).py
│   ├── test_bridge_gripper_timing.py
│   ├── test_cell_processing_continuous_motion.py
│   └── test_robodk_live_updater_identity.py
│
├── app.py
├── app_config.py
├── app_utils.py
├── calibration.py
├── camera_capture.py
├── drawing.py
├── final_slot_lock.py
├── frame_processing.py
├── Main.py
├── mediapipe_compat.py
├── object_names.py
├── README.md
├── robodk_compat.py
├── robodk_live_updater.py
├── robot_commands.py
├── robot_speed_profile.py
├── robot_worker.py
├── safety_control.py
├── StateMachine.py
├── station_bootstrap.py
├── station_config.py
├── station_helpers.py
├── station_logic.py
├── vision_detection.py
├── vision_worker.py
└── __init__.py

---
```
## Installation and Execution

This section explains how to install the required tools and how to run the robotic kitting workflow.

### Installation

1. Clone the repository to your local computer so that all project files are available:

```bash
git clone https://github.com/luisespcar/robotic-kitting.git
```

2. Open the downloaded project folder:

```bash
cd robotic-kitting
```

3. Install the required software:

- **Python**: used to run the control, coordination, and robot communication scripts.
- **MediaPipe**: used for hand detection and safety verification.
- **Anaconda**: used to manage the vision environment, video input, and camera execution.
- **RoboDK**: used to load and operate the digital twin of the robotic workstation.

4. Make sure the Anaconda environment used for the vision system is available. In this project, the environment is called:

```bash
vision_runtime
```

5. Activate the environment from an Anaconda Prompt:

```bash
conda activate vision_runtime
```

6. Install the required Python dependencies if they are not already installed:

```bash
pip install -r requirements.txt
```

---

### Execution

Follow these steps to run the system.

1. If the real robot is going to be used instead of simulation only, power on the UR10e robot and connect the computer to the robot using an Ethernet cable.

2. Open **RoboDK** and load the correct station file for this project. This file contains the digital twin of the robotic cell.

3. If physical execution is required, connect RoboDK to the real UR10e robot. If only simulation is required, the workflow can be tested directly in the digital twin.

4. Connect the camera to the computer so that the vision system can receive the video input.

5. Open an **Anaconda Prompt** and activate the project environment:

```bash
conda activate vision_runtime
```

6. Move to the folder where `Main.py` is located. For example:

```bash
cd path/to/robotic-kitting/ModularProgramming
```

7. Run the main script from this environment:

```bash
python Main.py
```

8. Once the robot, camera, and RoboDK station are ready, place the boxes and components in the workstation. The robotic kitting workflow can then be executed.

9. To repeat the process, run `Main.py` again from the Anaconda Prompt:

```bash
python Main.py
```

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
