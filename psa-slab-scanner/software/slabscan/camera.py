"""Camera backends: Raspberry Pi CSI cameras (Picamera2), USB/UVC (OpenCV), and a simulator.

Pi 5 has two CSI ports, so the front and back cameras are both Camera Module 3
(12 MP, autofocus). Focus is locked at a fixed lens position after calibration so
every slab is shot identically. Autofocus on glossy plastic hunts.
"""

from __future__ import annotations

from typing import Callable

import numpy as np


class PiCamera:
    def __init__(self, index: int, name: str, lens_position: float | None = None, exposure_us: int | None = None, gain: float | None = None, size: tuple[int, int] = (4608, 2592)):
        from picamera2 import Picamera2

        self.name = name
        self.cam = Picamera2(index)
        cfg = self.cam.create_still_configuration(main={"size": size, "format": "RGB888"}, buffer_count=2)
        self.cam.configure(cfg)
        controls: dict = {}
        if lens_position is not None:
            controls.update(AfMode=0, LensPosition=float(lens_position))  # 0 = manual focus
        if exposure_us is not None:
            controls.update(AeEnable=False, ExposureTime=int(exposure_us), AnalogueGain=float(gain or 1.0))
        self.cam.start()
        if controls:
            self.cam.set_controls(controls)

    def capture(self) -> np.ndarray:
        rgb = self.cam.capture_array("main")
        return rgb[:, :, ::-1].copy()  # -> BGR for OpenCV

    def close(self) -> None:
        self.cam.stop()
        self.cam.close()


class UsbCamera:
    def __init__(self, device: int | str, name: str, size: tuple[int, int] = (3840, 2160), focus: int | None = None):
        import cv2

        self.name = name
        self.cap = cv2.VideoCapture(device)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        if focus is not None:
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            self.cap.set(cv2.CAP_PROP_FOCUS, focus)

    def capture(self) -> np.ndarray:
        for _ in range(2):  # drop a stale buffered frame
            self.cap.grab()
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError(f"camera {self.name} returned no frame")
        return frame

    def close(self) -> None:
        self.cap.release()


class SimCamera:
    """Returns synthetic frames chosen by a callback (used by tests and dry runs)."""

    def __init__(self, name: str, frame_fn: Callable[[], np.ndarray]):
        self.name = name
        self._frame_fn = frame_fn

    def capture(self) -> np.ndarray:
        return self._frame_fn()

    def close(self) -> None:
        pass
