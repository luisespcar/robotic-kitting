"""Webcam opening, recovery and capture thread.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

import threading
import time

import cv2

from app_config import *

def open_webcam():
    indexes = CAMERA_SEARCH_INDEXES if AUTO_DETECT_CAMERA else [CAMERA_INDEX]
    last_error = None

    for idx in indexes:
        cap = cv2.VideoCapture(idx, CAMERA_BACKEND)

        if not cap.isOpened():
            last_error = f"No se pudo abrir cÃ¡mara Ã­ndice {idx}"
            cap.release()
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        ret, frame = cap.read()
        if ret and frame is not None:
            print(f"CÃ¡mara abierta correctamente: Ã­ndice {idx}")
            print(f"ResoluciÃ³n capturada: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
            print(f"FPS solicitado/aprox: {cap.get(cv2.CAP_PROP_FPS):.1f}")
            return cap, idx

        last_error = f"La cÃ¡mara Ã­ndice {idx} se abriÃ³ pero no entregÃ³ frames"
        cap.release()

    raise FileNotFoundError(
        "No se pudo abrir ninguna cÃ¡mara. Cambia CAMERA_INDEX a 0, 1, 2... "
        f"Ãšltimo error: {last_error}"
    )


def reopen_webcam(cap):
    try:
        if cap is not None:
            cap.release()
    except Exception:
        pass

    time.sleep(CAMERA_REOPEN_DELAY_S)
    return open_webcam()


class WebcamCaptureWorker:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._latest_frame = None
        self._latest_index = None
        self._latest_fps = float(CAMERA_FPS)
        self._last_error = None
        self._last_warning_ts = 0.0
        self.cap, self.opened_camera_index = open_webcam()
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps and fps > 1:
            self._latest_fps = float(fps)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def get_latest_frame(self):
        with self._lock:
            frame = self._latest_frame
            return frame, self._latest_index, self._latest_fps, self._last_error

    def stop(self, timeout=2.0):
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass

    def _warn(self, message):
        now = time.time()
        if now - self._last_warning_ts >= 1.0:
            print(message)
            self._last_warning_ts = now

    def _publish_frame(self, frame):
        with self._lock:
            self._latest_frame = frame
            self._latest_index = self.opened_camera_index
            self._last_error = None

    def _publish_error(self, message):
        with self._lock:
            self._last_error = message

    def _loop(self):
        camera_read_fail_count = 0

        while not self._stop_event.is_set():
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    camera_read_fail_count = 0
                    self._publish_frame(frame)
                    time.sleep(0.001)
                    continue

                camera_read_fail_count += 1
                self._publish_error(f"Camera read failed ({camera_read_fail_count})")
                self._warn(f"[Camara][AVISO] Fallo leyendo frame ({camera_read_fail_count}/{MAX_CAMERA_READ_FAILS_BEFORE_REOPEN})")

                if camera_read_fail_count >= MAX_CAMERA_READ_FAILS_BEFORE_REOPEN:
                    self._warn("[Camara][AVISO] Reabriendo cámara tras fallos consecutivos...")
                    self.cap, self.opened_camera_index = reopen_webcam(self.cap)
                    fps = self.cap.get(cv2.CAP_PROP_FPS)
                    if fps and fps > 1:
                        self._latest_fps = float(fps)
                    camera_read_fail_count = 0

                time.sleep(0.01)

            except Exception as exc:
                self._publish_error(str(exc))
                self._warn(f"[Camara][ERROR] {exc}")
                try:
                    self.cap, self.opened_camera_index = reopen_webcam(self.cap)
                except Exception as reopen_exc:
                    self._publish_error(str(reopen_exc))
                    self._warn(f"[Camara][ERROR] Reapertura fallida: {reopen_exc}")
                    time.sleep(CAMERA_REOPEN_DELAY_S)
