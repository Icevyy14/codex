"""Learned face-down check: does the card seen through the top of the slab show its BACK?

Every English Pokemon card has the same back (Japanese cards have another one), and the head camera sees the card
through the clear slab. Slabs whose face-down state is proven - a PSA back-label QR seen from above, or the
operator's confirmation - show what a face-down card looks like. A slab without a back QR whose card window looks
like one of them is face-down; a face-up slab shows its own card front instead.

Descriptor (``describe``). It has to be cheap and to survive what differs between two slabs with the same back:
  * Only ``face_down_window_mm``: rectangles on the slab plane, in mm from the head-camera axis, that lie on the
    card window. Not the label (it differs on every slab, and a face-up label is a label too), and not the head's
    own parts (cup, buffer, foot): those look the same in every frame, so they would make every slab match.
  * Each rectangle is cropped with a SEARCH_MM margin and resampled to WINDOW_PX_PER_MM (1 px per mm) with
    INTER_AREA. That box filter is the blur: sensor noise, focus, JPEG blocks and a 1 deg yaw (under 0.5 mm across
    the window) all vanish. Only the crop is resampled, so a 3264 x 2448 frame costs about as much as a thumbnail.
  * Saturated pixels are clipped, then the thumbnail minus its own Gaussian blur (sigma HIGHPASS_SIGMA_MM) is kept.
    Exposure, the ring light's fall-off and most of a glare spot are smooth, so they go; the printed pattern stays.
  * Pattern term: normalised cross-correlation (gain- and offset-invariant), taken at every shift up to
    +/-SEARCH_MM, best shift wins. The slab lies anywhere within about 2 mm in its pocket, and so did the reference.
  * Colour term: a hue-saturation histogram for colour frames (a dark-blue back against a yellow-, silver- or
    art-bordered front), or the shape of the normalised grey-level histogram for grey frames (the simulator).
  * score = the LOWER of the two. Both must agree. A false accept puts the cup on a card front; a false reject only
    stops the run. So the score leans toward reject.

Safety rules (``CardBackRefs`` and ``learned_match``):
  * References come only from QR-confirmed or operator-confirmed slabs (and the Phase 0 seed). A slab accepted by
    the learned match never becomes one, so the check cannot teach itself a wrong appearance.
  * A window with too little texture (blank, dark, washed out) neither matches nor becomes a reference.
  * The view over an empty pocket is kept as a baseline. A window that looks like the baseline does not show the
    slab (the head hides it): it neither matches nor becomes a reference.
  * The mode is active only with a measured threshold (``face_down_threshold``, from Phase 0) and at least
    ``face_down_min_refs`` references. Otherwise the run stops at every slab without a back QR, as in "stop" mode.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

WINDOW_PX_PER_MM = 1.0
SEARCH_MM = 4.0  # +/-2 mm in the pocket for this slab and for the reference, plus the 0.5 mm X calibration residual
HIGHPASS_SIGMA_MM = 4.0
MIN_TEXTURE = 3.0  # grey levels (std of the high-passed window); below = nothing printed in view
MIN_WINDOW_MM2 = 300.0  # smaller windows are too easy to match by chance
BASELINE_MAX = 0.5  # a window scoring this high against the empty-pocket view does not show the slab
CLUSTER_DEFAULT = 0.8  # similarity that joins a reference to a prototype while no threshold is measured
MAX_PROTOS = 6  # English back, Japanese back, and room for a few others (other games, holder types)
PER_PROTO = 8  # newest references kept per prototype (they follow the light as it drifts)
VERSION = 1
REF_SOURCES = ("qr", "operator", "phase0")  # never "learned"
FILE_NAME = "card_backs.npz"


@dataclass
class Descriptor:
    patches: list  # per window rectangle: float32 high-passed thumbnail, SEARCH_MM margin on every side
    hist: np.ndarray  # normalised histogram (colour: hue x saturation; grey: z-scored levels)
    texture: float  # mean std of the high-passed rectangles (inside the margin)
    color: bool


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


def _hist(cores: list[np.ndarray], color: bool) -> np.ndarray:
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
    patches, cores, tex = [], [], []
    for a, b, c, d in rects_img_mm:
        pa, pb, pc, pd = a - SEARCH_MM, b - SEARCH_MM, c + SEARCH_MM, d + SEARCH_MM
        X0, X1 = int(math.floor((pa - x0v) * sx)), int(math.ceil((pc - x0v) * sx))
        Y0, Y1 = int(math.floor((pb - y0v) * sy)), int(math.ceil((pd - y0v) * sy))
        if X0 < 0 or Y0 < 0 or X1 > w or Y1 > h or X1 - X0 < 4 or Y1 - Y0 < 4:
            return None
        tw, th = max(2 * m + 4, int(round((pc - pa) * WINDOW_PX_PER_MM))), max(2 * m + 4, int(round((pd - pb) * WINDOW_PX_PER_MM)))
        small = cv2.resize(frame[Y0:Y1, X0:X1], (tw, th), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if color else small
        g = np.minimum(gray.astype(np.float32), 250.0)
        hp = g - cv2.GaussianBlur(g, (0, 0), HIGHPASS_SIGMA_MM * WINDOW_PX_PER_MM)
        patches.append(hp)
        cores.append(small[m:th - m, m:tw - m])
        tex.append(float(hp[m:th - m, m:tw - m].std()))
    return Descriptor(patches, _hist(cores, color), float(np.mean(tex)), color)


def compare(q: Descriptor, r: Descriptor) -> Match:
    """Similarity of query ``q`` to reference ``r`` in [0, 1] (see the module docstring)."""
    if q is None or r is None or q.color != r.color or len(q.patches) != len(r.patches):
        return Match()
    if q.texture < MIN_TEXTURE or r.texture < MIN_TEXTURE:
        return Match()
    m = int(round(SEARCH_MM * WINDOW_PX_PER_MM))
    acc, wsum = None, 0.0
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


def signature(rects) -> str:
    """What a stored reference depends on: if the window or the descriptor changes, old references are useless."""
    return json.dumps({"v": VERSION, "rects": [list(map(float, r)) for r in rects], "ppm": WINDOW_PX_PER_MM, "search": SEARCH_MM,
                       "hp": HIGHPASS_SIGMA_MM})


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

    def best(self, d: Descriptor) -> Match:
        best = Match()
        for r in self.refs:
            m = compare(d, r.desc)
            if m.score > best.score:
                best = Match(m.score, m.ncc, m.hist, r.proto, r.source)
        return best

    def baseline_score(self, d: Descriptor) -> float:
        return compare(d, self.baseline).score if self.baseline is not None else 0.0

    def summary(self) -> str:
        p = self.protos()
        src = ", ".join(f"{k} {v}" for k, v in sorted(self.sources().items()))
        return f"{self.n_refs} references in {len(p)} prototype(s)" + (f" ({src})" if src else "")

    # ---- updates
    def set_baseline(self, d: Descriptor | None, meta: dict | None = None) -> None:
        if d is not None:
            self.baseline, self.baseline_meta = d, dict(meta or {})

    def add(self, d: Descriptor | None, source: str, meta: dict | None = None, cluster: float | None = None) -> tuple[int | None, str]:
        """Add a proven face-down slab's descriptor. Returns (prototype, "") or (None, why it was not used)."""
        if source not in REF_SOURCES:
            raise ValueError(f"reference source {source!r}: only {REF_SOURCES} slabs may become references")
        why = ""
        if d is None:
            why = "card window not in the frame"
        elif d.texture < MIN_TEXTURE:
            why = "nothing visible in the card window"
        elif self.baseline is not None and self.baseline_score(d) >= BASELINE_MAX:
            why = "card window looks like the empty-pocket view (the head hides it)"
        if why:
            self.rejected[why] = self.rejected.get(why, 0) + 1
            return None, why
        cluster = CLUSTER_DEFAULT if cluster is None else cluster
        m = self.best(d)
        if m.proto >= 0 and m.score >= cluster:
            proto = m.proto
        else:
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
        if self.refs:
            arrays["hist"] = np.stack([r.desc.hist for r in self.refs]).astype(np.float32)
            arrays["texture"] = np.array([r.desc.texture for r in self.refs], np.float32)
            arrays["color"] = np.array([r.desc.color for r in self.refs], bool)
            arrays["proto"] = np.array([r.proto for r in self.refs], np.int32)
            arrays["source"] = np.array([r.source for r in self.refs])
        if self.baseline is not None:
            for i, p in enumerate(self.baseline.patches):
                arrays[f"base_patch{i}"] = p.astype(np.float32)
            arrays["base_hist"] = self.baseline.hist.astype(np.float32)
            arrays["base_info"] = np.array([self.baseline.texture, float(self.baseline.color)], np.float32)
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
                    self.note = (f"{self.path.name} was made with another card window (face_down_window_mm changed): its references "
                                 "are not used; new ones are collected")
                    return
                meta = json.loads(str(z["meta"]))
                n = len(z["proto"]) if "proto" in z else 0
                n_rect = sum(1 for k in z.files if k.startswith("patch"))
                for j in range(n):
                    d = Descriptor([z[f"patch{i}"][j] for i in range(n_rect)], z["hist"][j], float(z["texture"][j]), bool(z["color"][j]))
                    self.refs.append(Ref(d, str(z["source"][j]), int(z["proto"][j]), (meta.get("refs") or [{}] * n)[j]))
                if "base_hist" in z:
                    nb = sum(1 for k in z.files if k.startswith("base_patch"))
                    info = z["base_info"]
                    self.baseline = Descriptor([z[f"base_patch{i}"] for i in range(nb)], z["base_hist"], float(info[0]), bool(info[1]))
                    self.baseline_meta = meta.get("baseline") or {}
                self.last_used = {int(k): float(v) for k, v in (meta.get("last_used") or {}).items()}
                self._next_proto = max([int(meta.get("next_proto", 0))] + [r.proto + 1 for r in self.refs])
                self.note = f"loaded {self.summary()} from {self.path}"
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
            self.refs, self.baseline = [], None
            self.note = f"could not read {self.path} ({type(e).__name__}: {e}): starting with no references"


def learned_ready(refs: CardBackRefs, threshold: float | None, min_refs: int, rects) -> str:
    """Why the learned check cannot accept anything yet ("" = it can)."""
    if threshold is None:
        return "learned check not active yet: face_down_threshold is not measured (Phase 0 measures it)"
    if window_area(rects) < MIN_WINDOW_MM2:
        return f"learned check not active: the card window face_down_window_mm is only {window_area(rects):.0f} mm2 (needs {MIN_WINDOW_MM2:.0f})"
    if refs.baseline is None:
        return "learned check not active yet: no view over an empty pocket to compare with"
    if refs.n_refs < min_refs:
        extra = ""
        if refs.rejected:
            extra = " (" + "; ".join(f"{n} confirmed slab(s) not used: {k}" for k, n in refs.rejected.items()) + ")"
        return f"learned check not active yet: {refs.n_refs} of {min_refs} card-back references{extra}"
    return ""


def learned_match(refs: CardBackRefs, d: Descriptor | None, threshold: float | None, min_refs: int, rects) -> tuple[bool, str, Match]:
    """The learned decision for a slab without a back QR. Returns (accept, reason if not, best match)."""
    if threshold is None or window_area(rects) < MIN_WINDOW_MM2:
        return False, learned_ready(refs, threshold, min_refs, rects), Match()
    if d is None:
        return False, "learned check: the card window is not inside the frame", Match()
    if d.texture < MIN_TEXTURE:
        return False, "learned check: nothing visible in the card window (blank, dark or washed out)", Match()
    if refs.baseline is not None:
        base = refs.baseline_score(d)
        if base >= BASELINE_MAX:
            return False, f"learned check: the card window looks like the view over an empty pocket ({base:.2f}): the head hides it", Match()
    why = learned_ready(refs, threshold, min_refs, rects)
    if why:
        return False, why, Match()
    m = refs.best(d)
    if m.score < threshold:
        return False, f"learned check: best match with a known card back {m.score:.2f} < threshold {threshold:.2f}", m
    return True, "", m
