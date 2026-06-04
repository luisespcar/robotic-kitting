"""Background worker for asynchronous vision processing.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import threading

from frame_processing import process_frame

class VisionProcessingWorker:
    def __init__(
        self,
        model,
        bridge_model,
        hand_detector,
        rois_data,
        camera_matrix,
        dist_coeffs,
        bridge_homography,
        bridge_homography_data,
        bridge_stabilizer,
    ):
        self.model = model
        self.bridge_model = bridge_model
        self.hand_detector = hand_detector
        self.rois_data = rois_data
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.bridge_homography = bridge_homography
        self.bridge_homography_data = bridge_homography_data
        self.bridge_stabilizer = bridge_stabilizer
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._stop_event = threading.Event()
        self._latest_frame = None
        self._latest_packet = None
        self._busy = False
        self._last_error = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, frame):
        if frame is None:
            return
        with self._lock:
            self._latest_frame = frame
        self._event.set()

    def consume_latest_packet(self):
        with self._lock:
            packet = self._latest_packet
            self._latest_packet = None
        return packet

    def is_busy(self):
        with self._lock:
            return self._busy

    def stop(self, timeout=2.0):
        self._stop_event.set()
        self._event.set()
        self._thread.join(timeout=timeout)

    def _pop_latest_frame(self):
        with self._lock:
            frame = self._latest_frame
            self._latest_frame = None
            self._busy = frame is not None
        return frame

    def _set_idle(self):
        with self._lock:
            self._busy = False

    def _loop(self):
        while not self._stop_event.is_set():
            self._event.wait(timeout=0.1)
            self._event.clear()

            while not self._stop_event.is_set():
                frame = self._pop_latest_frame()
                if frame is None:
                    self._set_idle()
                    break

                try:
                    output, station_state, detections, bridge_detections, robot_detections, robot_state, hand_state = process_frame(
                        self.model,
                        self.bridge_model,
                        self.hand_detector,
                        frame,
                        self.rois_data,
                        self.camera_matrix,
                        self.dist_coeffs,
                        self.bridge_homography,
                        self.bridge_homography_data,
                        self.bridge_stabilizer,
                    )
                    packet = {
                        "output": output,
                        "results": station_state,
                        "detections": detections,
                        "bridge_detections": bridge_detections,
                        "robot_detections": robot_detections,
                        "robot_state": robot_state,
                        "hand_state": hand_state,
                    }
                    with self._lock:
                        self._latest_packet = packet
                        self._last_error = None
                except Exception as exc:
                    with self._lock:
                        self._last_error = str(exc)
                    print(f"[VisionProcessingWorker][ERROR] {exc}")
                finally:
                    self._set_idle()
