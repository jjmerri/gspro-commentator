"""Reads a putt's break from GSPro's green grid.

On the green GSPro draws a grid whose white dots creep slowly downhill along its lines. A still frame
says nothing (a vision model guessed at random), but a quick burst of frames does: matching each dot
to itself in the next frame gives its drift. Dots on the cross lines move sideways (the break), dots
on the lines running away from the golfer move toward or away (uphill or downhill).

The putt's path is a strip from the ball (bottom middle of the screen) up to the hole, split into
thirds so a putt that breaks one way then the other is caught. Dots wrap back to the uphill side of
their cell once they reach its edge; that jump is far bigger than a frame's drift, so the nearest-
neighbour match drops it. Gentle drift can't be told from a flat putt yet, so that stays silent.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from PIL import Image

from .config import PuttReadConfig, Region

# The strip the putt rolls through, as fractions of the screen: up from the ball (GSPro centres it,
# low on the screen) toward the hole, narrowing with the perspective. Only the box around it is
# grabbed and searched; a bigger one makes the burst and the dot search several times slower.
BALL_X, STRIP_TOP, STRIP_BOTTOM, STRIP_HALF = 0.50, 0.595, 0.91, 0.096
REGION = Region(left=0.39, top=0.58, width=0.22, height=0.34)
# Pixel sizes are for a 4K screen (2160 tall) and scaled to the one read.
REF_HEIGHT = 2160
MAX_STEP = 15        # px a dot can move between frames; more is a wrap or a different dot
MIN_STEP = 0.5       # px; less is a dot sitting still
DOT_PIXELS = (6, 400)
SECTIONS = ("near the ball", "in the middle", "furthest up")


@dataclass
class Drift:
    right: int = 0
    left: int = 0
    dx: float = 0.0   # mean sideways px per frame, + is to the right

    @property
    def steps(self) -> int:
        return self.right + self.left


@dataclass
class PuttRead:
    sections: list[Drift] = field(default_factory=list)   # near the ball, middle, furthest up
    uphill: int = 0      # dots on the lines toward the golfer creeping toward them
    downhill: int = 0
    dy: float = 0.0      # their mean drift, px per frame, + is toward the golfer (uphill)
    frames: int = 0
    seconds: float = 0.0

    def facts(self, cfg: PuttReadConfig, slope: bool = True) -> list[str]:
        """`slope` False leaves out uphill/downhill (the HUD's measured elevation says it better)."""
        out = []
        dirs = [_direction(d, cfg) for d in self.sections]
        known = [(i, d) for i, d in enumerate(dirs) if d]
        if known:
            hard = max(abs(self.sections[i].dx) for i, _ in known)
            how = ("severely" if hard >= cfg.severe_px else "hard" if hard >= cfg.hard_px
                   else "a little" if hard < cfg.moderate_px else "")
            way = {"right": "left to right", "left": "right to left"}
            first, at = known[0][1], tuple(i for i, _ in known)
            if all(d == first for _, d in known):
                # On a long putt the hole is above the capture, so "late" is further up, not at the cup.
                where = {(0, 1, 2): "all the way", (0,): "early, off the putter", (0, 1): "early",
                         (1, 2): "later on", (2,): "later on"}.get(at, "")
                out.append(" ".join(f"Putt read: it breaks {how} {way[first]} {where}".split()) + ".")
            else:
                second = next(d for _, d in known if d != first)
                out.append(f"Putt read: a double breaker, it starts {way[first]} then turns back "
                           f"{way[second]}.")
        total = self.uphill + self.downhill
        if slope and total >= cfg.min_steps and abs(self.dy) >= cfg.slope_px:
            if self.uphill >= cfg.slope_share * total:
                out.append("Putt read: it's uphill.")
            elif self.downhill >= cfg.slope_share * total:
                out.append("Putt read: it's downhill.")
        return out


def _direction(d: Drift, cfg: PuttReadConfig) -> str | None:
    if d.steps < cfg.min_steps or abs(d.dx) < cfg.gentle_px:
        return None
    side = "right" if d.dx > 0 else "left"
    if max(d.right, d.left) < cfg.slope_share * d.steps:
        return None
    return side


def dots(img: Image.Image, k: float = 1.0):
    """The grid's white dots as an (n, 2) array of centres in pixels. `k` is the screen's height over
    a 4K screen's."""
    import numpy as np

    from .minimap import _components

    a = np.asarray(img.convert("RGB"))
    h, w, _ = a.shape
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # Pale and grey: white dots, not the yellowish turf. (Per-channel, as a.min(axis=2) is slow.)
    lo, hi = np.minimum(np.minimum(r, g), b), np.maximum(np.maximum(r, g), b)
    m = (lo > 165) & (hi - lo < 35)   # uint8 is safe: hi >= lo
    out = []
    small, big = max(2, round(DOT_PIXELS[0] * k * k)), DOT_PIXELS[1] * k * k
    for ys, xs in _components(m, small):
        hh, ww = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if len(ys) < big and 0.5 < hh / ww < 2:
            out.append((xs.mean(), ys.mean()))
    return np.array(out).reshape(-1, 2)


def read_break(frames: list[Image.Image]) -> PuttRead:
    """`frames` are grabs of REGION, a few hundredths of a second apart (in the order taken)."""
    import numpy as np

    started = time.perf_counter()
    read = PuttRead(sections=[Drift() for _ in SECTIONS], frames=len(frames))
    if len(frames) < 2:
        return read
    w, h = frames[0].size
    k = h / REGION.height / REF_HEIGHT
    seq = [dots(f, k) for f in frames]
    steps = []
    for a, b in zip(seq, seq[1:]):
        if len(a) == 0 or len(b) == 0:
            continue
        d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        fwd, back = d2.argmin(axis=1), d2.argmin(axis=0)
        for i, j in enumerate(fwd):
            if back[j] == i and d2[i, j] < (MAX_STEP * k) ** 2:
                steps.append((*a[i], *(b[j] - a[i])))
    if not steps:
        read.seconds = time.perf_counter() - started
        return read
    v = np.array(steps)
    v[:, 2:] /= k   # drift in 4K pixels
    v = v[np.hypot(v[:, 2], v[:, 3]) > MIN_STEP]
    x = REGION.left + v[:, 0] / w * REGION.width
    y = REGION.top + v[:, 1] / h * REGION.height
    dx, dy = v[:, 2], v[:, 3]
    # The strip narrows toward the hole with the perspective.
    t = (y - STRIP_TOP) / (STRIP_BOTTOM - STRIP_TOP)
    strip = (t > 0) & (t < 1) & (np.abs(x - BALL_X) < STRIP_HALF * (0.4 + 0.6 * t))
    sideways = strip & (np.abs(dx) > 2 * np.abs(dy))
    updown = strip & (np.abs(dy) > 2 * np.abs(dx))
    read.uphill, read.downhill = int((dy[updown] > 0).sum()), int((dy[updown] < 0).sum())
    read.dy = float(dy[updown].mean()) if updown.any() else 0.0
    for k, d in enumerate(read.sections):
        # Thirds by distance up the screen: the first is nearest the ball (the bottom).
        s = sideways & (t <= 1 - k / 3) & (t > 1 - (k + 1) / 3)
        d.right, d.left = int((dx[s] > 0).sum()), int((dx[s] < 0).sum())
        d.dx = float(dx[s].mean()) if s.any() else 0.0
    read.seconds = time.perf_counter() - started
    return read
