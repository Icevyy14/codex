"""Learned face-down check: does the card seen through the top of the slab show its BACK?

Every English Pokemon card has the same back (Japanese cards have another one), and the head camera sees the card
through the clear slab. Slabs whose face-down state is proven - a back-label code seen from above (a PSA or CGC back QR,
the CGC 2020-23 back barcode), or the operator's confirmation - show what a face-down card looks like. A slab without a
back-label code whose card window looks like one of them is face-down; a face-up slab shows its own card front instead.

Descriptor (``describe``). It has to be cheap and to survive what differs between two slabs with the same back:
  * Only ``face_down_window_mm``: rectangles on the slab plane, in mm from the head-camera axis, that lie on the
    card window. Not the label (it differs on every slab, and a face-up label is a label too), and not the head's
    own parts (cup, buffer, foot): those look the same in every frame, so they would make every slab match.
  * Each rectangle is cropped with a SEARCH_MM margin and resampled to WINDOW_PX_PER_MM (1 px per mm) with
    INTER_AREA. That box filter is the blur: sensor noise, focus, JPEG blocks and a 1 deg yaw (under 0.5 mm across
    the window) all vanish. Only the crop is resampled, so a 3264 x 2448 frame costs about as much as a thumbnail.
  * Glare (thumbnail pixels at GLARE_LEVEL or above, grown by GLARE_DILATE_MM) is masked: it counts nowhere, not in
    the pattern, the colour or the texture. Then the thumbnail minus its own Gaussian blur (sigma HIGHPASS_SIGMA_MM,
    taken over unmasked pixels only) is kept. Exposure, the ring light's fall-off and the halo of a glare spot are
    smooth, so they go; the printed pattern stays.
  * Pattern term: normalised cross-correlation (gain- and offset-invariant), taken at every shift up to
    +/-SEARCH_MM, best shift wins. The slab lies anywhere within about 2 mm in its pocket, and so did the reference.
  * Colour term: a hue-saturation histogram for colour frames (a dark-blue back against a yellow-, silver- or
    art-bordered front), or the shape of the normalised grey-level histogram for grey frames (the simulator).
  * score = the LOWER of the two. Both must agree. A false accept puts the cup on a card front; a false reject only
    stops the run. So the score leans toward reject.
  * The grey thumbnail itself is kept too (``levels``, same crop): it shows what moves with the camera.

Safety rules (``CardBackRefs``, ``learned_ready`` and ``learned_match``):
  * References come only from QR-confirmed or operator-confirmed slabs (and the Phase 0 seed). A slab accepted by
    the learned match never becomes one, so the check cannot teach itself a wrong appearance. The runner learns from a
    proven slab only once it was placed and its read agrees (Runner._settle_reference): a back-label code from another
    slab's label in view, or a back code seen from below, teaches nothing. A back design known only from operator
    confirmations is matched once OPERATOR_PROTO_MIN slabs confirm it (one wrong confirmation alone teaches nothing).
  * A match needs MATCH_K references (different slabs) of ONE back design at the threshold, not just the best one. On
    64 real slabs one odd back (a card sitting low in its holder: only blue swirl in the window) matched a blue
    Water-type front at 0.56-0.62 against a 0.55 floor; the second-best back never came above 0.44. So one odd or one
    wrong reference cannot let a front through, and a new back design is matched only once a second slab joins it.
  * A window with too little texture (blank, dark, washed out) or too much glare neither matches nor becomes a
    reference. A match also needs at least TEXTURE_RATIO of the matched back design's own texture: a plain card
    front with a glare spot has some texture, but far less than a card back.
  * The view over an empty pocket is kept as a baseline. A window whose PATTERN looks like the baseline's does not
    show the slab (the head hides it): it neither matches nor becomes a reference. Only the pattern term counts here:
    the empty pocket's grey levels never look like a slab's, so the colour term would always say "different".
  * A head part can also hide only part of the window, or show no pattern of its own. So the levels of the newest
    proven slabs are compared with the baseline, pixel by pixel, inside the window: a pixel that relates to the
    baseline by the frame's common exposure ratio on (almost) every proven slab moves with the camera, so it is not
    the slab. If more than STATIC_MAX of the window is like that, the mode is not active. (Only inside the window:
    the margin holds the card's flat border and the slab's clear plastic, which do that too, harmlessly.)
  * The camera's aim, on that same view over an empty pocket (``aim_problem``): only the pad far below may show in the
    middle of the card window and just beyond its cup-side edge. A tilt toward the cup brings the cup pad and the foot
    in there (each mm of clearance is about 0.39 deg of tilt). With an edge there the mode is not active and nothing is
    learned, until a run's view over an empty pocket is clear again. A verdict counts only for the run that took it
    (``CardBackRefs.stale``): a resume whose survey finds no empty pocket accepts nothing and learns nothing until it
    looks over the first source pocket it empties, as after a failed check. So a camera knocked while the run was
    stopped is seen. Its limits [Certain, sim and geometry]:
      - A part as dark as the pad shows no edge, and nothing catches it while it covers a strip of the window. The
        camera-locked check above does not: at 1 px per mm the strip's pixels are part and card mixed, so they do not
        follow the empty view's levels (a foot at the pad's grey over 9-26 % of the window read 0.3-0.9 % camera-locked).
      - Only a tilt TOWARD the cup is checked. A tilt away from it, or a roll along the row, moves the window toward the
        card top or off the card's side, and nothing here sees that.
      - AIM_EDGE and AIM_MAX_MM2 were set on the simulator's flat, noiseless empty view. Lint, dust specks of about
        1 mm, glue blotches or a sharp shadow on a real pad can make it fire. That is safe (the learned check stays off,
        every slab without a back code stops) but needs a real empty-pocket frame to tune.
  * The mode is active only with a measured threshold (``face_down_threshold``, from Phase 0, at least
    THRESHOLD_FLOOR) that was measured for this card window (``face_down_threshold_sig`` = ``threshold_tag``), at
    least ``face_down_min_refs`` references, and the head's view checked on STATIC_REFS proven slabs on this machine.
    Otherwise the run stops at every slab without a back QR, as in "stop" mode.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .config import FACE_DOWN_THRESHOLD_FLOOR as THRESHOLD_FLOOR  # no measured threshold below it is used

WINDOW_PX_PER_MM = 1.0
SEARCH_MM = 4.0  # +/-2 mm in the pocket for this slab and for the reference, plus the 0.5 mm X calibration residual
HIGHPASS_SIGMA_MM = 4.0
MIN_TEXTURE = 3.0  # grey levels (std of the high-passed window); below = nothing printed in view
TEXTURE_RATIO = 0.5  # a match needs this fraction of the matched back design's median texture [Guessing: sim backs 19-26, plain front + glare 7-8]
MIN_WINDOW_MM2 = 300.0  # smaller windows are too easy to match by chance
BASELINE_MAX = 0.5  # pattern similarity (ncc) to the empty-pocket view at which a window does not show the slab
GLARE_LEVEL = 245.0  # thumbnail grey level (a 1 mm box average) counted as glare: a saturated reflection of the ring light
GLARE_DILATE_MM = 2.0  # the mask grows by this much (the bright halo around the saturated core)
GLARE_REF_MAX = 0.02  # a frame with more of the window under glare never becomes a reference (a fixed reflection would be in every one)
GLARE_QUERY_MAX = 0.30  # a frame with more of the window under glare is not matched: the run stops
STATIC_MAX = 0.10  # fraction of the window that may move with the camera (head part, anything fixed to it)
STATIC_REFS = 5  # proven slabs seen on THIS machine before that is measured (the newest STATIC_USE are used)
STATIC_USE = 12
STATIC_VOTE = 0.8  # a pixel moves with the camera if it does so on this fraction of those slabs
STATIC_LOG_TOL = 0.08  # +/-8 % around the frame's common exposure ratio
OPERATOR_PROTO_MIN = 3  # a back design known only from operator confirmations is matched once this many confirm it
# Camera aim, checked on the view over an empty pocket (``aim_problem``). A tilt toward the cup slides the card window (fixed
# in the image) toward the cup pad and the foot: each mm of clearance is ~0.39 deg (cad/checks.py check_camera_aim). Over an
# empty pocket at the travel height (pad ~388 mm under the lens) the window also reaches this pocket's own rods (their
# feet project 15.9-18.9 mm from the axis along the row) and, beyond them, the neighbouring pockets: only the middle of the
# window shows nothing but this pocket's pad there [Certain, CAD rod and pocket positions].
AIM_HALF_ROW_MM = 12.0  # the part of the window checked: up to this far from the camera axis along the row ...
AIM_BAND_MM = 1.0  # ... over its whole height, plus this much beyond its cup-side edge (where a tilt brings the head in)
AIM_EDGE = 4.0  # grey levels of the high-passed thumbnail: a part's edge against the pad (a smooth shadow or fall-off is not)
AIM_MAX_MM2 = 2.0  # more than this many mm2 of such edges = a head part (or dirt on the pad) where only pad should show
MATCH_K = 2  # a match needs this many references (different slabs) of one back design at the threshold [Certain, real slabs at the
# machine's scale, 332 face-up frames with and without glare: k=1 accepted 3 at 0.55 (max 0.62), k=2 none (max 0.44); backs of other
# slabs accepted 223 of 252 instead of 239]
CLUSTER_DEFAULT = 0.8  # similarity that joins a reference to a prototype while no threshold is measured
MAX_PROTOS = 6  # English back, Japanese back, and room for a few others (other games, holder types)
PER_PROTO = 8  # newest references kept per prototype (they follow the light as it drifts)
VERSION = 2  # 2: glare mask, levels; files of version 1 are not used
REF_SOURCES = ("qr", "operator", "phase0")  # never "learned"
FILE_NAME = "card_backs.npz"


@dataclass
class Descriptor:
    patches: list  # per window rectangle: float32 high-passed thumbnail, SEARCH_MM margin on every side; 0 under glare
    hist: np.ndarray  # normalised histogram (colour: hue x saturation; grey: z-scored levels), glare left out
    texture: float  # mean std of the high-passed rectangles (inside the margin, glare left out)
    color: bool
    levels: list = field(default_factory=list)  # per rectangle: float32 grey thumbnail, same crop as the patch (no high-pass)
    glare: float = 0.0  # fraction of the window under the glare mask


@dataclass
class Match:
    score: float = 0.0
    ncc: float = 0.0
    hist: float = 0.0
    proto: int = -1
    source: str = ""


@dataclass
class Ref:
    desc: Descriptor
    source: str
    proto: int
    meta: dict = field(default_factory=dict)


def window_area(rects) -> float:
    return float(sum(max(0.0, x1 - x0) * max(0.0, y1 - y0) for x0, y0, x1, y1 in rects))


def frame_view_mm(shape, distance_mm: float, spec: dict | None = None, cam=None) -> tuple[float, float, float, float]:
    """The frame's extent on the slab plane ``distance_mm`` from the lens: (x0, y0, x1, y1) in mm, image axes (x to
    the right, y down), relative to the camera axis. A camera may report it (the simulator's ``view_rect_mm``); a
    real one is centred on its axis and spans hfov_deg across its width."""
    if cam is not None and hasattr(cam, "view_rect_mm"):
        return tuple(float(v) for v in cam.view_rect_mm(distance_mm))
    h, w = shape[:2]
    hx = distance_mm * math.tan(math.radians(float((spec or {}).get("hfov_deg", 64.0)) / 2))
    hy = hx * h / w
    return (-hx, -hy, hx, hy)


def image_rects(rects, row_axis: str = "x") -> list[tuple[float, float, float, float]]:
    """face_down_window_mm is given as (along the row, along the slab) with the label end negative. For row_axis "x"
    that is the image's own (x, y) with the label at the top; for "y" the two are swapped (label at the left)."""
    out = []
    for x0, y0, x1, y1 in rects:
        out.append((float(y0), float(x0), float(y1), float(x1)) if row_axis == "y" else (float(x0), float(y0), float(x1), float(y1)))
    return out


def threshold_tag(rects) -> str:
    """What a measured face_down_threshold depends on: the card window and the descriptor. phase0 --save writes it as
    face_down_threshold_sig; a threshold with another tag (or none) is not used."""
    return hashlib.sha1(signature(rects).encode()).hexdigest()[:12]


def _glare_ok(gray: np.ndarray) -> np.ndarray:
    """True where a thumbnail pixel is not glare: below GLARE_LEVEL, and not within GLARE_DILATE_MM of a pixel that is."""
    glare = (gray >= GLARE_LEVEL).astype(np.uint8)
    r = int(round(GLARE_DILATE_MM * WINDOW_PX_PER_MM))
    if glare.any() and r > 0:
        glare = cv2.dilate(glare, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    return glare == 0


def _highpass(gray: np.ndarray, region: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(high-passed thumbnail, mask of the pixels that are not glare). The blur is a normalised convolution over the
    unmasked pixels, so a glare spot neither shows as pattern nor drags its neighbours' local mean up. ``region``: only
    these pixels count at all (aim_problem)."""
    ok = _glare_ok(gray) if region is None else (_glare_ok(gray) & region)
    w = ok.astype(np.float32)
    g = np.minimum(gray, 250.0)
    s = HIGHPASS_SIGMA_MM * WINDOW_PX_PER_MM
    low = cv2.GaussianBlur(g * w, (0, 0), s) / np.maximum(cv2.GaussianBlur(w, (0, 0), s), 1e-3)
    return (g - low) * w, ok


def _hist(cores: list[np.ndarray], color: bool) -> np.ndarray:
    """``cores``: the unmasked window pixels, (n, 3) BGR or (n,) grey per rectangle."""
    if sum(len(c) for c in cores) < 16:
        return np.zeros(36 if color else 16, np.float32)
    if color:
        hsv = cv2.cvtColor(np.concatenate([c.reshape(-1, 1, 3) for c in cores]), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        keep = (hsv[:, 2] > 25) & (hsv[:, 2] < 245)  # not black, not glare
        hsv = hsv[keep] if keep.sum() >= 16 else hsv
        h, _, _ = np.histogram2d(hsv[:, 0].astype(np.float32), hsv[:, 1].astype(np.float32), bins=(12, 3), range=((0, 180), (0, 256)))
        h = h.ravel()
    else:
        v = np.concatenate([c.ravel() for c in cores]).astype(np.float32)
        z = (v - v.mean()) / max(float(v.std()), 1e-3)
        h, _ = np.histogram(np.clip(z, -2.5, 2.5), bins=16, range=(-2.5, 2.5))
    h = h.astype(np.float32)
    return h / max(float(h.sum()), 1.0)


def draw_window(frame: np.ndarray, rects_img_mm, view_mm) -> np.ndarray:
    """The frame with the window rectangles drawn in red: they must lie on the card, clear of the label and the head."""
    x0v, y0v, x1v, y1v = view_mm
    h, w = frame.shape[:2]
    out = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    for a, b, c, d in rects_img_mm:
        p0 = (int((a - x0v) / (x1v - x0v) * w), int((b - y0v) / (y1v - y0v) * h))
        p1 = (int((c - x0v) / (x1v - x0v) * w), int((d - y0v) / (y1v - y0v) * h))
        cv2.rectangle(out, p0, p1, (0, 0, 255), max(2, w // 400))
    return out


def describe(frame: np.ndarray, rects_img_mm, view_mm) -> Descriptor | None:
    """Descriptor of the window rectangles (image-axis mm, see ``image_rects``) in a frame whose extent on the slab
    plane is ``view_mm`` (``frame_view_mm``). None if a rectangle (with its search margin) is not inside the frame."""
    if frame is None or not len(rects_img_mm):
        return None
    h, w = frame.shape[:2]
    x0v, y0v, x1v, y1v = view_mm
    sx, sy = w / (x1v - x0v), h / (y1v - y0v)
    color = frame.ndim == 3 and frame.shape[2] >= 3
    m = int(round(SEARCH_MM * WINDOW_PX_PER_MM))
    patches, cores, tex, levels = [], [], [], []
    n_glare = n_core = 0
    for a, b, c, d in rects_img_mm:
        pa, pb, pc, pd = a - SEARCH_MM, b - SEARCH_MM, c + SEARCH_MM, d + SEARCH_MM
        X0, X1 = int(math.floor((pa - x0v) * sx)), int(math.ceil((pc - x0v) * sx))
        Y0, Y1 = int(math.floor((pb - y0v) * sy)), int(math.ceil((pd - y0v) * sy))
        if X0 < 0 or Y0 < 0 or X1 > w or Y1 > h or X1 - X0 < 4 or Y1 - Y0 < 4:
            return None
        tw, th = max(2 * m + 4, int(round((pc - pa) * WINDOW_PX_PER_MM))), max(2 * m + 4, int(round((pd - pb) * WINDOW_PX_PER_MM)))
        small = cv2.resize(frame[Y0:Y1, X0:X1], (tw, th), interpolation=cv2.INTER_AREA)
        gray = (cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if color else small).astype(np.float32)
        hp, ok = _highpass(gray)
        core = (slice(m, th - m), slice(m, tw - m))
        keep = ok[core]
        patches.append(hp)
        levels.append(gray)
        cores.append(small[core][keep])
        tex.append(float(hp[core][keep].std()) if keep.sum() >= 16 else 0.0)
        n_glare += int(keep.size - keep.sum())
        n_core += int(keep.size)
    return Descriptor(patches, _hist(cores, color), float(np.mean(tex)), color, levels, n_glare / max(n_core, 1))


def compare(q: Descriptor, r: Descriptor) -> Match:
    """Similarity of query ``q`` to reference ``r`` in [0, 1] (see the module docstring)."""
    if q is None or r is None or q.color != r.color or len(q.patches) != len(r.patches):
        return Match()
    if q.texture < MIN_TEXTURE or r.texture < MIN_TEXTURE:
        return Match()
    m = int(round(SEARCH_MM * WINDOW_PX_PER_MM))
    acc, wsum = None, 0.0
    # Glare pixels are 0 in both patches: they count as "no pattern here". That does NOT only lower a score: it also
    # drops the pixels that disagreed most, and the colour term loses them too, so a score can rise. On a real blue
    # Water-type front a glare spot raised 0.56 to 0.62 and 0.43 to 0.55 (MATCH_K is what keeps those out). A
    # correlation over only the pixels valid in both lifts glare frames further: in the simulator face-up fronts with
    # glare went from 0.39 to 0.48.
    for qp, rp in zip(q.patches, r.patches):
        if qp.shape != rp.shape:
            return Match()
        tpl = rp[m:rp.shape[0] - m, m:rp.shape[1] - m]
        res = cv2.matchTemplate(qp, tpl, cv2.TM_CCOEFF_NORMED)
        acc = res * tpl.size if acc is None else acc + res * tpl.size
        wsum += tpl.size
    ncc = float(np.nan_to_num(acc / wsum, nan=-1.0, posinf=-1.0, neginf=-1.0).max())
    hist = float(np.minimum(q.hist, r.hist).sum())
    return Match(max(0.0, min(ncc, hist)), ncc, hist)


def _camera_locked(level: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Pixels of one frame whose level relates to the empty-pocket view's by the frame's common exposure ratio (the
    mode of the log ratio, +/-STATIC_LOG_TOL). Whatever moves with the camera - a part of the head - does that at any
    exposure; the card under it does not, because the pocket below is far darker or brighter than a card and the slab
    lies a little differently every time. Glare (and clipped pixels) never counts."""
    ok = (level < GLARE_LEVEL) & (base < GLARE_LEVEL)
    if ok.sum() < 16:
        return np.zeros(level.shape, bool)
    q = np.log((level + 2.0) / (base + 2.0))
    h, edges = np.histogram(q[ok], bins=np.arange(-6.0, 6.0 + 1e-6, 0.05))
    k = int(np.argmax(h))
    return ok & (np.abs(q - 0.5 * (edges[k] + edges[k + 1])) <= STATIC_LOG_TOL)


def aim_problem(base: Descriptor | None, rects_img_mm, slab_axis: str = "y") -> str:
    """Is the card window clear of the head on the view over an empty pocket (``base``, described with the same
    ``rects_img_mm``)? "" = clear, else why not. ``slab_axis``: the image axis along the slab ("y" when row_axis is "x").

    Checked: the middle of each window rectangle along the row (AIM_HALF_ROW_MM), over its whole height and AIM_BAND_MM
    beyond its edge nearer the camera axis (the cup side). There only this pocket's pad, out of focus far below, may
    show: smooth, so its high-passed thumbnail (the descriptor's own term) stays near zero. A head part has an edge
    against the pad, darker or brighter. A part that matches the pad's grey level shows no edge, and is not seen. Only
    the cup side is checked: a tilt away from the cup or a roll along the row is not (module docstring)."""
    if base is None or not base.levels:
        return "the card window is not inside the head camera's view over an empty pocket (check cam_head and face_down_window_mm)"
    n = 0
    worst = 0.0
    for (a, b, c, d), lv in zip(rects_img_mm, base.levels):
        h, w = lv.shape
        xs = (a - SEARCH_MM) + (np.arange(w) + 0.5) * (c - a + 2 * SEARCH_MM) / w  # pixel centres, mm (image axes)
        ys = (b - SEARCH_MM) + (np.arange(h) + 0.5) * (d - b + 2 * SEARCH_MM) / h
        row, slab = (xs[None, :], ys[:, None]) if slab_axis == "y" else (ys[:, None], xs[None, :])
        r0, r1, s0, s1 = (a, c, b, d) if slab_axis == "y" else (b, d, a, c)
        if abs(s1) <= abs(s0):  # the window lies on the label side of the axis: its cup-side edge is the one nearer 0
            s1 += AIM_BAND_MM
        else:
            s0 -= AIM_BAND_MM
        region = (np.abs(row) <= AIM_HALF_ROW_MM) & (row >= r0) & (row <= r1) & (slab >= s0) & (slab <= s1)
        if region.sum() < 4:
            continue
        hp, ok = _highpass(lv, region)
        edges = np.abs(hp[ok])
        n += int((edges >= AIM_EDGE).sum())
        worst = max(worst, float(edges.max()) if edges.size else 0.0)
    mm2 = n / WINDOW_PX_PER_MM ** 2
    if mm2 <= AIM_MAX_MM2:
        return ""
    return (f"over an empty pocket the head camera sees edges where only the pad should show, in the card window or within "
            f"{AIM_BAND_MM:g} mm of its cup side ({mm2:.0f} mm2, up to {worst:.0f} grey levels): a part of the head is in the window, "
            "or about to be. The head camera is tilted toward the cup, or something lies on the pad there (lint, dust, a tag): "
            "look at the picture first")


def signature(rects) -> str:
    """What a stored reference depends on: if the window or the descriptor changes, old references are useless."""
    return json.dumps({"v": VERSION, "rects": [list(map(float, r)) for r in rects], "ppm": WINDOW_PX_PER_MM, "search": SEARCH_MM,
                       "hp": HIGHPASS_SIGMA_MM, "glare": [GLARE_LEVEL, GLARE_DILATE_MM]})


class CardBackRefs:
    """Reference descriptors of proven face-down slabs, grouped in prototypes (one per back design), persisted in an
    .npz file (``path``; None = in memory only, e.g. the simulator). ``rects`` = face_down_window_mm (row-axis
    order; it only identifies the geometry the references were taken with)."""

    def __init__(self, path: Path | str | None = None, rects=(), log=None):
        self.path = Path(path) if path else None
        self.sig = signature(rects)
        self.refs: list[Ref] = []
        self.last_used: dict[int, float] = {}
        self.baseline: Descriptor | None = None
        self.baseline_meta: dict = {}
        # why the stored view over an empty pocket (and its aim verdict) does not count for this run ("" = it does). Set
        # when a run's survey starts (Runner.survey), cleared by its view over an empty pocket (set_baseline): only a
        # resume can be left without one. Never saved: the file keeps the last real check.
        self.stale = ""
        self.rejected: dict[str, int] = {}  # why confirmed slabs were not taken as references (for the report)
        self.note = ""  # what load() found
        self._next_proto = 0
        self._log = log or (lambda *_: None)
        if self.path is not None and self.path.exists():
            self.load()

    # ---- queries
    @property
    def n_refs(self) -> int:
        return len(self.refs)

    def protos(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for r in self.refs:
            out[r.proto] = out.get(r.proto, 0) + 1
        return out

    def sources(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.refs:
            out[r.source] = out.get(r.source, 0) + 1
        return out

    def usable(self, proto: int) -> bool:
        """A prototype may be matched against: it holds a QR-proven (or Phase 0) back, or OPERATOR_PROTO_MIN operator ones."""
        src = [r.source for r in self.refs if r.proto == proto]
        return any(s != "operator" for s in src) or len(src) >= OPERATOR_PROTO_MIN

    def proto_texture(self, proto: int) -> float:
        t = [r.desc.texture for r in self.refs if r.proto == proto]
        return float(np.median(t)) if t else 0.0

    def ranked(self, d: Descriptor, usable_only: bool = False) -> dict[int, list[Match]]:
        """Per prototype: the matches of ``d`` with its references, best first, one per slab (its cert; the same slab
        scanned twice is one slab)."""
        ok = {p: self.usable(p) for p in self.protos()} if usable_only else {}
        per: dict[int, dict[str, Match]] = {}
        for i, r in enumerate(self.refs):
            if usable_only and not ok[r.proto]:
                continue
            m = compare(d, r.desc)
            key = str(r.meta.get("cert") or "") or f"#{i}"
            got = per.setdefault(r.proto, {})
            if key not in got or m.score > got[key].score:
                got[key] = Match(m.score, m.ncc, m.hist, r.proto, r.source)
        return {p: sorted(v.values(), key=lambda x: -x.score) for p, v in per.items()}

    def best(self, d: Descriptor, usable_only: bool = False, k: int = 1) -> Match:
        """The prototype whose k-th best slab matches best, and that match (k = 1: the single best reference)."""
        best = Match()
        for ms in self.ranked(d, usable_only).values():
            if len(ms) >= k and ms[k - 1].score > best.score:
                best = ms[k - 1]
        return best

    def baseline_score(self, d: Descriptor) -> float:
        """Pattern similarity (ncc) of a window to the empty-pocket view: high = the head's own parts fill it."""
        return max(0.0, compare(d, self.baseline).ncc) if self.baseline is not None else 0.0

    def static_fraction(self) -> tuple[float | None, int]:
        """(fraction of the window that moves with the camera, proven slabs it was measured on). The fraction is None
        until STATIC_REFS slabs proven on this machine (QR or operator, not the Phase 0 jig) have levels to compare."""
        base = self.baseline
        refs = [r for r in self.refs if r.source in ("qr", "operator") and r.desc.levels][-STATIC_USE:]
        if base is None or not base.levels or len(refs) < STATIC_REFS:
            return None, len(refs)
        m = int(round(SEARCH_MM * WINDOW_PX_PER_MM))
        core = lambda levels: np.concatenate([x[m:x.shape[0] - m, m:x.shape[1] - m].ravel() for x in levels])  # noqa: E731
        b = core(base.levels)
        votes = np.zeros(b.shape, np.float32)
        n = 0
        for r in refs:
            lv = core(r.desc.levels)
            if lv.shape == b.shape:
                votes += _camera_locked(lv, b)
                n += 1
        if n < STATIC_REFS:
            return None, n
        return float(np.mean(votes >= STATIC_VOTE * n)), n

    def summary(self) -> str:
        p = self.protos()
        src = ", ".join(f"{k} {v}" for k, v in sorted(self.sources().items()))
        return f"{self.n_refs} references in {len(p)} prototype(s)" + (f" ({src})" if src else "")

    # ---- updates
    def set_baseline(self, d: Descriptor | None, meta: dict | None = None) -> None:
        if d is not None:
            self.baseline, self.baseline_meta, self.stale = d, dict(meta or {}), ""

    def add(self, d: Descriptor | None, source: str, meta: dict | None = None, cluster: float | None = None) -> tuple[int | None, str]:
        """Add a proven face-down slab's descriptor. Returns (prototype, "") or (None, why it was not used)."""
        if source not in REF_SOURCES:
            raise ValueError(f"reference source {source!r}: only {REF_SOURCES} slabs may become references")
        why = ""
        if d is None:
            why = "card window not in the frame"
        elif d.texture < MIN_TEXTURE:
            why = "nothing visible in the card window"
        elif d.glare > GLARE_REF_MAX:
            why = "glare on the card window"
        elif self.baseline is not None and self.baseline_score(d) >= BASELINE_MAX:
            why = "card window looks like the empty-pocket view (the head hides it)"
        elif self.baseline is not None and self.baseline_meta.get("aim"):
            why = "the head camera's aim puts a part of the head in the card window"
        elif self.baseline is not None and self.stale:
            why = "the head camera's aim is not checked this run yet"
        if why:
            self.rejected[why] = self.rejected.get(why, 0) + 1
            return None, why
        cluster = CLUSTER_DEFAULT if cluster is None else cluster
        m = self.best(d)
        if m.proto >= 0 and m.score >= cluster:
            proto = m.proto
        else:  # a new back design (or an odd slab): it holds one slab, so it matches nothing until a second joins (MATCH_K)
            proto = self._next_proto
            self._next_proto += 1
            if len(self.protos()) >= MAX_PROTOS:  # evict the prototype used least recently
                old = min(self.protos(), key=lambda k: self.last_used.get(k, 0.0))
                self.refs = [r for r in self.refs if r.proto != old]
                self.last_used.pop(old, None)
        self.refs.append(Ref(d, source, proto, dict(meta or {}, t=round(time.time(), 1))))
        members = [i for i, r in enumerate(self.refs) if r.proto == proto]
        if len(members) > PER_PROTO:
            del self.refs[members[0]]  # the oldest of this prototype
        self.touch(proto)
        return proto, ""

    def drop(self, cert: str | None = None, source: str | None = None) -> int:
        """Remove the references of one cert (its ``meta["cert"]``) or of one source. Returns how many went."""
        keep = [r for r in self.refs if not ((cert is not None and str(r.meta.get("cert", "")) == str(cert)) or (source is not None and r.source == source))]
        n = len(self.refs) - len(keep)
        self.refs = keep
        return n

    def touch(self, proto: int) -> None:
        self.last_used[proto] = time.time()

    # ---- file
    def save(self) -> None:
        if self.path is None:
            return
        arrays: dict[str, np.ndarray] = {"sig": np.array(self.sig)}
        n_rect = len(self.refs[0].desc.patches) if self.refs else 0
        for i in range(n_rect):
            arrays[f"patch{i}"] = np.stack([r.desc.patches[i] for r in self.refs]).astype(np.float32)
            arrays[f"level{i}"] = np.stack([r.desc.levels[i] for r in self.refs]).astype(np.float32)
        if self.refs:
            arrays["hist"] = np.stack([r.desc.hist for r in self.refs]).astype(np.float32)
            arrays["texture"] = np.array([r.desc.texture for r in self.refs], np.float32)
            arrays["glare"] = np.array([r.desc.glare for r in self.refs], np.float32)
            arrays["color"] = np.array([r.desc.color for r in self.refs], bool)
            arrays["proto"] = np.array([r.proto for r in self.refs], np.int32)
            arrays["source"] = np.array([r.source for r in self.refs])
        if self.baseline is not None:
            for i, p in enumerate(self.baseline.patches):
                arrays[f"base_patch{i}"] = p.astype(np.float32)
                arrays[f"base_level{i}"] = self.baseline.levels[i].astype(np.float32)
            arrays["base_hist"] = self.baseline.hist.astype(np.float32)
            arrays["base_info"] = np.array([self.baseline.texture, float(self.baseline.color), self.baseline.glare], np.float32)
        arrays["meta"] = np.array(json.dumps({"refs": [r.meta for r in self.refs], "last_used": {str(k): v for k, v in self.last_used.items()},
                                              "next_proto": self._next_proto, "baseline": self.baseline_meta}))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("wb") as f:
            np.savez(f, **arrays)
        tmp.replace(self.path)

    def load(self) -> None:
        try:
            with np.load(self.path, allow_pickle=False) as z:
                if str(z["sig"]) != self.sig:
                    self.note = (f"{self.path.name} was made with another card window (face_down_window_mm changed) or an older "
                                 "version of the check: its references are not used; new ones are collected")
                    return
                meta = json.loads(str(z["meta"]))
                n = len(z["proto"]) if "proto" in z else 0
                n_rect = sum(1 for k in z.files if k.startswith("patch"))
                for j in range(n):
                    d = Descriptor([z[f"patch{i}"][j] for i in range(n_rect)], z["hist"][j], float(z["texture"][j]), bool(z["color"][j]),
                                   [z[f"level{i}"][j] for i in range(n_rect)], float(z["glare"][j]))
                    self.refs.append(Ref(d, str(z["source"][j]), int(z["proto"][j]), (meta.get("refs") or [{}] * n)[j]))
                if "base_hist" in z:
                    nb = sum(1 for k in z.files if k.startswith("base_patch"))
                    info = z["base_info"]
                    self.baseline = Descriptor([z[f"base_patch{i}"] for i in range(nb)], z["base_hist"], float(info[0]), bool(info[1]),
                                               [z[f"base_level{i}"] for i in range(nb)], float(info[2]))
                    self.baseline_meta = meta.get("baseline") or {}
                self.last_used = {int(k): float(v) for k, v in (meta.get("last_used") or {}).items()}
                self._next_proto = max([int(meta.get("next_proto", 0))] + [r.proto + 1 for r in self.refs])
                self.note = f"loaded {self.summary()} from {self.path}"
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
            self.refs, self.baseline = [], None
            self.note = f"could not read {self.path} ({type(e).__name__}: {e}): starting with no references"


def _threshold_problem(threshold: float | None, rects, tag: str | None) -> str:
    if threshold is None:
        return "learned check not active yet: face_down_threshold is not measured (Phase 0 measures it)"
    if threshold < THRESHOLD_FLOOR:
        return f"learned check not active: face_down_threshold {threshold:.2f} is below the floor {THRESHOLD_FLOOR:.2f}"
    if tag != threshold_tag(rects):
        return ("learned check not active: face_down_threshold was not measured for this card window (face_down_threshold_sig "
                f"{tag or 'missing'}, this window and check {threshold_tag(rects)}): run Phase 0 again with --save")
    if window_area(rects) < MIN_WINDOW_MM2:
        return f"learned check not active: the card window face_down_window_mm is only {window_area(rects):.0f} mm2 (needs {MIN_WINDOW_MM2:.0f})"
    return ""


def _aim_refusal(refs: CardBackRefs) -> str:
    """The aim check's verdict on the stored view over an empty pocket (Runner._take_baseline runs aim_problem on it):
    a head part in the window makes every frame alike, so nothing may be accepted. A verdict from before a resume is
    stale (CardBackRefs.stale): nothing is accepted until this run has looked over an empty pocket."""
    if refs.baseline is not None and refs.stale:
        return f"learned check not active: {refs.stale}"
    aim = refs.baseline_meta.get("aim") if refs.baseline is not None else None
    if not aim:
        return ""
    return (f"learned check not active: {aim}. Re-aim the head camera (BUILD_GUIDE 7.7), then compare images/face_down_empty.jpg "
            f"(pocket {refs.baseline_meta.get('pocket', '?')}) with images/face_down_window.jpg. Dirt on that pocket's pad looks the same: clean it")


def learned_ready(refs: CardBackRefs, threshold: float | None, min_refs: int, rects, tag: str | None = None) -> str:
    """Why the learned check cannot accept anything yet ("" = it can). ``tag``: face_down_threshold_sig."""
    why = _threshold_problem(threshold, rects, tag)
    if why:
        return why
    if refs.baseline is None:
        return "learned check not active yet: no view over an empty pocket to compare with"
    why = _aim_refusal(refs)
    if why:
        return why
    if refs.n_refs < min_refs:
        extra = ""
        if refs.rejected:
            extra = " (" + "; ".join(f"{n} confirmed slab(s) not used: {k}" for k, n in refs.rejected.items()) + ")"
        return f"learned check not active yet: {refs.n_refs} of {min_refs} card-back references{extra}"
    frac, n = refs.static_fraction()
    if frac is None:
        return (f"learned check not active yet: the head's view of the card window is checked on {STATIC_REFS} slabs proven face-down "
                f"on this machine (back-label code or your confirmation), {n} so far")
    if frac > STATIC_MAX:
        return (f"learned check not active: {100 * frac:.0f}% of the card window shows the same thing on every proven slab as over an empty "
                f"pocket (allowed {100 * STATIC_MAX:.0f}%): a part of the head is in the way. Compare images/face_down_window.jpg with "
                "images/face_down_empty.jpg; the head must leave face_down_window_mm clear")
    return ""


def learned_match(refs: CardBackRefs, d: Descriptor | None, threshold: float | None, min_refs: int, rects,
                  tag: str | None = None) -> tuple[bool, str, Match]:
    """The learned decision for a slab without a back QR. Returns (accept, reason if not, best match)."""
    why = _threshold_problem(threshold, rects, tag) or _aim_refusal(refs)
    if why:
        return False, why, Match()
    if d is None:
        return False, "learned check: the card window is not inside the frame", Match()
    if d.texture < MIN_TEXTURE:
        return False, "learned check: nothing visible in the card window (blank, dark or washed out)", Match()
    if d.glare > GLARE_QUERY_MAX:
        return False, f"learned check: glare covers {100 * d.glare:.0f}% of the card window", Match()
    if refs.baseline is not None:
        base = refs.baseline_score(d)
        if base >= BASELINE_MAX:
            return False, f"learned check: the card window looks like the view over an empty pocket ({base:.2f}): the head hides it", Match()
    why = learned_ready(refs, threshold, min_refs, rects, tag)
    if why:
        return False, why, Match()
    ranked = refs.ranked(d, usable_only=True)
    m = Match()  # the design whose MATCH_K-th best slab matches best
    for ms in ranked.values():
        if len(ms) >= MATCH_K and ms[MATCH_K - 1].score > m.score:
            m = ms[MATCH_K - 1]
    if m.score < threshold:
        everything = refs.best(d)
        if everything.score >= threshold and not refs.usable(everything.proto):
            n = refs.protos().get(everything.proto, 0)
            return False, (f"learned check: it matches a card back ({everything.score:.2f}) known only from {n} of your confirmations; "
                           f"it is used once {OPERATOR_PROTO_MIN} confirm it"), everything
        one = max((ms[0] for ms in ranked.values()), key=lambda x: x.score, default=Match())
        if one.score >= threshold:
            n = sum(x.score >= threshold for x in ranked[one.proto])
            return False, (f"learned check: only {n} known card back(s) of one design match it ({one.score:.2f}); a match needs "
                           f"{MATCH_K} slabs of that design at the threshold {threshold:.2f} (one odd reference, or a card front that "
                           "looks like one, is not enough)"), one
        return False, f"learned check: best match with a known card back {one.score:.2f} < threshold {threshold:.2f}", one
    tex = refs.proto_texture(m.proto)
    if d.texture < TEXTURE_RATIO * tex:
        return False, (f"learned check: the card window shows far less pattern (texture {d.texture:.1f}) than that card back "
                       f"({tex:.1f}): a plain card front, or glare"), m
    return True, "", m
