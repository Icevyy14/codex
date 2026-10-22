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

    def lens_range(self) -> tuple[float, float, float] | None:
        """(min, max, default) LensPosition in dioptres as the camera reports it, or None (fixed-focus module)."""
        r = self.cam.camera_controls.get("LensPosition")
        return tuple(float(v) for v in r) if r else None

    def set_lens_position(self, dioptres: float) -> None:
        """Manual focus: 1 / distance in metres (0 = infinity). 140 mm -> about 7.1."""
        self.cam.set_controls({"AfMode": 0, "LensPosition": float(dioptres)})

    def capture(self) -> np.ndarray:
        rgb = self.cam.capture_array("main")
        return rgb[:, :, ::-1].copy()  # -> BGR for OpenCV

    def close(self) -> None:
        self.cam.stop()
        self.cam.close()


def find_usb_camera() -> str | None:
    """Stable path of the first USB (UVC) camera, e.g. /dev/v4l/by-id/usb-..._video-index0.

    On a Pi 5 the CSI camera pipeline registers /dev/video0..7 itself, so "device 0" is usually
    NOT the USB camera. The by-id path also survives replugging and reboots."""
    import glob

    paths = sorted(glob.glob("/dev/v4l/by-id/usb-*-video-index0"))
    return paths[0] if paths else None


class UsbCamera:
    def __init__(self, device: int | str, name: str, size: tuple[int, int] = (3264, 2448), focus: int | None = None):
        import sys

        import cv2

        self.name = name
        if device == "auto":
            found = find_usb_camera()
            if found is None:
                raise RuntimeError(f"camera {name}: no USB camera under /dev/v4l/by-id (is it plugged in? try `v4l2-ctl --list-devices`)")
            device = found
        self.device = device
        if sys.platform.startswith("linux"):
            self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        else:
            self.cap = cv2.VideoCapture(device)
        if not self.cap.isOpened():
            raise RuntimeError(f"camera {name}: cannot open {device}")
        # Full-resolution modes of UVC boards like the IMX179 are MJPEG-only; YUYV falls back to a small size.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # fewer stale frames from before the LED ring came on
        self.actual_size = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
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
