"""Spielfeld (Digital Twin der Umgebung): Startfeld, Suchsegment, Knochen, Schiedsrichter."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import Config
from .geometry import dist_point_segment, field_excess, sector_excess, wrap
from .plant import Plant


@dataclass
class Bone:
    x: float = 2.5
    y: float = 0.0
    th: float = 0.4

    def ends(self, length: float):
        dx, dy = math.cos(self.th) * length / 2, math.sin(self.th) * length / 2
        return self.x - dx, self.y - dy, self.x + dx, self.y + dy


class World:
    def __init__(self, cfg: Config, plant: Plant):
        self.cfg = cfg
        self.plant = plant
        self.bone = Bone()
        # Schiedsrichter steht VOR dem Gesicht des Hundes (FAQ 14): Hund schaut nach -x
        self.referee = [-cfg.env.referee_distance, 0.0]
        self.referee_radius = 0.20

    # -------------------------------------------------------------- Aufbau
    def place_bone(self, x: float, y: float, th: float | None = None) -> None:
        self.bone.x, self.bone.y = x, y
        if th is not None:
            self.bone.th = th

    def random_bone(self, rng: random.Random, rmin: float = 0.9, rmax: float | None = None, inner: float = 0.85) -> Bone:
        """Zufaellige Lage im Suchsegment (gleichverteilt nach Flaeche), mit Randabstand."""
        f = self.cfg.field
        rmax = rmax if rmax is not None else f.sector_radius - 0.3
        half = self.cfg.sector_half * inner
        r = math.sqrt(rng.uniform(rmin ** 2, rmax ** 2))
        a = self.cfg.sector_axis + rng.uniform(-half, half)
        self.bone = Bone(r * math.cos(a), r * math.sin(a), rng.uniform(-math.pi, math.pi))
        return self.bone

    def set_referee_distance(self, d: float) -> None:
        self.referee = [-d, 0.0]
        self.cfg.env.referee_distance = d

    # -------------------------------------------------------------- Geometrie / Sensorik
    def robot_point(self, fwd: float, left: float = 0.0):
        p = self.plant
        c, s = math.cos(p.th), math.sin(p.th)
        return p.x + c * fwd - s * left, p.y + s * fwd + c * left

    def bone_view(self):
        """(Peilung rad, Distanz m) der Knochenmitte aus Sicht der Kamera (links positiv)."""
        r = self.cfg.robot
        cx, cy = self.robot_point(r.camera_offset)
        dx, dy = self.bone.x - cx, self.bone.y - cy
        d = math.hypot(dx, dy)
        return wrap(math.atan2(dy, dx) - self.plant.th), d

    def contact(self) -> bool:
        """Beruehrt die Nase / Vorderkante den Knochen?"""
        r, f = self.cfg.robot, self.cfg.field
        ax, ay, bx, by = self.bone.ends(f.bone_length)
        pts = [self.robot_point(r.nose_offset), self.robot_point(r.front_edge, r.width / 2),
               self.robot_point(r.front_edge, -r.width / 2)]
        lim = f.bone_width / 2 + 0.005
        return any(dist_point_segment(px, py, ax, ay, bx, by) <= lim for px, py in pts)

    def tof(self) -> float | None:
        """Wahre Distanz des Einpunkt-Sensors (Strahl nach vorn) zum naechsten Hindernis."""
        r, f = self.cfg.robot, self.cfg.field
        ox, oy = self.robot_point(r.nose_offset - 0.02)
        h = self.plant.th
        ux, uy = math.cos(h), math.sin(h)
        best = None
        half_beam = math.radians(self.cfg.robot.tof_beam_deg) / 2

        def circle(cx, cy, rad):
            vx, vy = cx - ox, cy - oy
            t = vx * ux + vy * uy
            if t <= 0:
                return None
            perp = abs(vx * uy - vy * ux)
            if perp <= rad + t * math.tan(half_beam):
                return max(t - math.sqrt(max(rad * rad - perp * perp, 0.0)), 0.0) if perp < rad else t
            return None

        d = circle(self.referee[0], self.referee[1], self.referee_radius)
        if d is not None:
            best = d
        # Knochen als Strecke: Abtastung
        ax, ay, bx, by = self.bone.ends(f.bone_length)
        for i in range(0, 8):
            px, py = ax + (bx - ax) * i / 7, ay + (by - ay) * i / 7
            vx, vy = px - ox, py - oy
            t = vx * ux + vy * uy
            if t > 0 and abs(vx * uy - vy * ux) <= f.bone_width / 2 + t * math.tan(half_beam):
                best = t if best is None else min(best, t)
        if best is not None and best <= self.cfg.robot.tof_range:
            return best
        return None

    # -------------------------------------------------------------- Regeln
    def field_excess(self, x: float | None = None, y: float | None = None) -> float:
        f = self.cfg.field
        x = self.plant.x if x is None else x
        y = self.plant.y if y is None else y
        return field_excess(x, y, self.cfg.sector_half, f.sector_radius, self.cfg.sector_axis,
                            f.start_field_l, f.start_field_w)

    def in_start_field(self, margin: float = 0.0) -> bool:
        f = self.cfg.field
        return abs(self.plant.x) <= f.start_field_l / 2 + margin and abs(self.plant.y) <= f.start_field_w / 2 + margin

    def bone_in_sector(self) -> bool:
        return sector_excess(self.bone.x, self.bone.y, self.cfg.sector_half, self.cfg.field.sector_radius,
                             self.cfg.sector_axis) == 0.0
