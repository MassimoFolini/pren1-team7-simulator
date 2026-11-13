"""Kleine 2D-Geometrie-Helfer (Meter, Radiant)."""
from __future__ import annotations

import math
from dataclasses import dataclass


def wrap(a: float) -> float:
    """Winkel auf (-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    th: float = 0.0

    def as_tuple(self):
        return (self.x, self.y, self.th)


def dist_point_segment(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0.0, 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def sector_excess(x: float, y: float, half: float, radius: float, axis: float = 0.0) -> float:
    """Abstand eines Punktes zum Suchsegment (Scheitel im Ursprung), 0 wenn innen."""
    r = math.hypot(x, y)
    if r < 1e-9:
        return 0.0
    a = abs(wrap(math.atan2(y, x) - axis))
    if a <= half:
        return max(0.0, r - radius)
    if a < math.pi / 2:
        e = r * math.sin(a - half)          # Abstand zur naechsten Kante
        return math.hypot(e, max(0.0, r * math.cos(a - half) - radius)) if r * math.cos(a - half) > radius else e
    return r                                  # hinter dem Scheitel


def rect_excess(x: float, y: float, l: float, w: float) -> float:
    """Abstand zum Startfeld-Rechteck (Laenge l entlang x, Breite w entlang y, zentriert)."""
    dx = max(abs(x) - l / 2, 0.0)
    dy = max(abs(y) - w / 2, 0.0)
    return math.hypot(dx, dy)


def field_excess(x: float, y: float, half: float, radius: float, axis: float, sl: float, sw: float) -> float:
    return min(sector_excess(x, y, half, radius, axis), rect_excess(x, y, sl, sw))
