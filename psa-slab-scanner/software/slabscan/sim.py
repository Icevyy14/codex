"""Synthetic PSA-style label images for testing without real slabs or hardware.

These are NOT pixel copies of real PSA labels. PSA does not publish its layout or
symbology. They are stand-ins with realistic size, code size and failure modes
(glare, blur, tilt, low resolution), used to prove the decode pipeline and to size
the camera. ``tools/calibrate.py`` checks the same pipeline against real slabs.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import zxingcpp

PX_PER_MM_RENDER = 40  # render resolution before degradation
LABEL_W_MM, LABEL_H_MM = 70.0, 20.0
SLAB_W_MM, SLAB_H_MM = 80.3, 135.5
LABEL_TOP_MM = 5.0  # label offset from slab top edge (guess - calibrate on real slabs)


def _symbol(text: str, fmt: str, module_mm: float, height_mm: float | None = None) -> np.ndarray:
    """Render a symbol with a given module size in mm at PX_PER_MM_RENDER."""
    bc = zxingcpp.create_barcode(text, getattr(zxingcpp.BarcodeFormat, fmt))
    img = np.array(zxingcpp.write_barcode_to_image(bc, scale=1, add_quiet_zones=True))
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = module_mm * PX_PER_MM_RENDER
    w = max(1, int(round(img.shape[1] * scale)))
    if height_mm is None:  # 2D symbol: square modules
        h = max(1, int(round(img.shape[0] * scale)))
    else:  # 1D symbol: stretch bars to the requested height
        img = img[:1, :] if img.shape[0] > 1 else img
        h = int(round(height_mm * PX_PER_MM_RENDER))
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_NEAREST)


def _paste(canvas: np.ndarray, sym: np.ndarray, x_mm: float, y_mm: float) -> None:
    x, y = int(x_mm * PX_PER_MM_RENDER), int(y_mm * PX_PER_MM_RENDER)
    h, w = sym.shape
    h = min(h, canvas.shape[0] - y)
    w = min(w, canvas.shape[1] - x)
    canvas[y:y + h, x:x + w] = np.minimum(canvas[y:y + h, x:x + w], sym[:h, :w])


def _text(canvas: np.ndarray, s: str, x_mm: float, y_mm: float, size_mm: float) -> None:
    scale = size_mm * PX_PER_MM_RENDER / 22.0
    cv2.putText(canvas, s, (int(x_mm * PX_PER_MM_RENDER), int(y_mm * PX_PER_MM_RENDER)), cv2.FONT_HERSHEY_SIMPLEX, scale, 0, max(1, int(scale * 2)), cv2.LINE_AA)


def render_label(cert: str, side: str = "front", symbology: str = "Code128", module_mm: float = 0.25) -> np.ndarray:
    """Grayscale label at PX_PER_MM_RENDER. side='front' -> 1D code, side='back' -> QR + 1D."""
    canvas = np.full((int(LABEL_H_MM * PX_PER_MM_RENDER), int(LABEL_W_MM * PX_PER_MM_RENDER)), 245, np.uint8)
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1] - 1, canvas.shape[0] - 1), 120, 6)
    if side == "front":
        _text(canvas, "2023 POKEMON SV151", 3, 5, 2.4)
        _text(canvas, "#199 CHARIZARD EX", 3, 9, 2.4)
        _text(canvas, "SPECIAL ILLUS. RARE", 3, 13, 2.4)
        _text(canvas, "GEM MT 10", 50, 6, 2.6)
        bar = _symbol(cert, symbology, module_mm, height_mm=4.5)
        _paste(canvas, bar, LABEL_W_MM - 3 - bar.shape[1] / PX_PER_MM_RENDER, 8.5)
        _text(canvas, cert, 52, 18, 2.4)
    else:
        qr = _symbol(f"https://www.psacard.com/cert/{cert}", "QRCode", 0.42)
        _paste(canvas, qr, 2, (LABEL_H_MM - qr.shape[0] / PX_PER_MM_RENDER) / 2)
        _text(canvas, "PSA", 30, 9, 4)
        bar = _symbol(cert, symbology, module_mm, height_mm=3.5)
        _paste(canvas, bar, LABEL_W_MM - 2 - bar.shape[1] / PX_PER_MM_RENDER, 12)
        _text(canvas, cert, 52, 10, 2.2)
    return canvas


@dataclass
class Degrade:
    mm_per_px: float = 0.06  # camera resolution on the slab
    blur_px: float = 0.8  # gaussian sigma in output pixels (defocus/motion)
    tilt_deg: float = 4.0  # perspective tilt of the slab vs. sensor
    rotate_deg: float = 1.5  # in-plane rotation (slab not square in slot)
    glare: float = 0.0  # 0..1 strength of a specular hot spot
    glare_pos: tuple[float, float] = (0.5, 0.5)  # hot-spot centre, fraction of label
    noise: float = 3.0  # gaussian sensor noise (8-bit levels)
    jpeg_quality: int = 90
    haze: float = 0.12  # slab plastic lowers contrast


def slab_view(cert: str, side: str, deg: Degrade, symbology: str = "Code128", module_mm: float = 0.25, seed: int = 0) -> np.ndarray:
    """Camera view of the top ~45 mm of a slab (label + border), degraded."""
    rng = np.random.default_rng(seed)
    label = render_label(cert, side, symbology, module_mm)
    view_w_mm, view_h_mm = SLAB_W_MM + 10, 45.0
    canvas = np.full((int(view_h_mm * PX_PER_MM_RENDER), int(view_w_mm * PX_PER_MM_RENDER)), 40, np.uint8)
    sx, sy = 5.0, 2.0  # slab corner within view
    cv2.rectangle(canvas, (int(sx * PX_PER_MM_RENDER), int(sy * PX_PER_MM_RENDER)), (int((sx + SLAB_W_MM) * PX_PER_MM_RENDER), canvas.shape[0]), 70, -1)
    lx = sx + (SLAB_W_MM - LABEL_W_MM) / 2
    ly = sy + LABEL_TOP_MM
    y0, x0 = int(ly * PX_PER_MM_RENDER), int(lx * PX_PER_MM_RENDER)
    canvas[y0:y0 + label.shape[0], x0:x0 + label.shape[1]] = label
    img = canvas.astype(np.float32)
    img = img * (1 - deg.haze) + 255 * deg.haze * 0.5
    if deg.glare > 0:
        gx = (lx + deg.glare_pos[0] * LABEL_W_MM) * PX_PER_MM_RENDER
        gy = (ly + deg.glare_pos[1] * LABEL_H_MM) * PX_PER_MM_RENDER
        yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
        r2 = ((xx - gx) / (14 * PX_PER_MM_RENDER)) ** 2 + ((yy - gy) / (6 * PX_PER_MM_RENDER)) ** 2
        img = img + 255 * deg.glare * np.exp(-r2)
    img = np.clip(img, 0, 255).astype(np.uint8)
    h, w = img.shape
    t = np.tan(np.radians(deg.tilt_deg)) * 0.5
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * t * 0.3, 0], [w * (1 - t * 0.3), h * t * 0.2], [w, h], [0, h * (1 - t * 0.2)]])
    img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=40)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg.rotate_deg, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=40)
    scale = 1.0 / (deg.mm_per_px * PX_PER_MM_RENDER)
    out = cv2.resize(img, (max(8, int(w * scale)), max(8, int(h * scale))), interpolation=cv2.INTER_AREA)
    if deg.blur_px > 0:
        out = cv2.GaussianBlur(out, (0, 0), deg.blur_px)
    out = np.clip(out.astype(np.float32) + rng.normal(0, deg.noise, out.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, deg.jpeg_quality])
    return cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
