"""Physikalisches Modell des Roboters ("Strecke"): Antrieb, Encoder, Gyro, Haltungsaktor, Akku.

Die Strecke kennt die WAHRE Pose. Die Software (Firmware/Brain) sieht nur Encoder, Gyro und Sensoren
und muss mit Drift und Rauschen zurechtkommen.
"""
from __future__ import annotations

import math
import random

from .config import Config
from .geometry import clamp, wrap


class Plant:
    def __init__(self, cfg: Config, rng: random.Random):
        r = cfg.robot
        self.cfg = cfg
        self.rng = rng
        # wahre (leicht abweichende) Parameter -> Odometrie-Drift
        self.r_l = r.wheel_radius * (1 + rng.uniform(-r.wheel_radius_err, r.wheel_radius_err))
        self.r_r = r.wheel_radius * (1 + rng.uniform(-r.wheel_radius_err, r.wheel_radius_err))
        self.track = r.track * (1 + rng.uniform(-r.track_err, r.track_err))
        self.gyro_bias = math.radians(rng.uniform(-r.gyro_bias_dps, r.gyro_bias_dps))
        # wahre Pose (Start: Mitte Startfeld, Kopf weg vom Suchbereich = 180 Grad)
        self.x, self.y, self.th = 0.0, 0.0, math.pi
        self.wl = 0.0            # Radwinkelgeschwindigkeit rad/s
        self.wr = 0.0
        self.phi_l = 0.0         # Radwinkel rad
        self.phi_r = 0.0
        self.u_l = 0.0           # Motor-Duty -1..1
        self.u_r = 0.0
        self.power_on = True     # Antriebsleistung (Not-Aus schaltet ab)
        self.v = 0.0
        self.w = 0.0
        # Haltung
        self.pose = "STAND"      # Endlage
        self.pose_from = "STAND"
        self.pose_to = "STAND"
        self.pose_prog = 1.0
        self.pose_dur = 1.0
        self.frozen = False      # Not-Aus: Aktorik eingefroren
        self.show = ""           # Ausdruck (Schwanz/Ohren)
        self.show_end = 0.0
        # Energie
        self.energy_wh = 0.0
        self.t = 0.0

    # ---------------------------------------------------------------- Haltung
    def set_pose(self, target: str) -> bool:
        if self.frozen:
            return False
        if target == self.pose and self.pose_prog >= 1.0:
            return True
        r = self.cfg.robot
        cur = self.pose if self.pose_prog >= 1.0 else self.pose_to
        dur = {"SITZ": r.t_sit, "PLATZ": r.t_down, "STAND": r.t_stand}[target]
        if cur == "PLATZ" and target == "SITZ":
            dur = r.t_sit
        self.pose_from = cur
        self.pose_to = target
        self.pose_prog = 0.0
        self.pose_dur = dur
        return True

    @property
    def pose_busy(self) -> bool:
        return self.pose_prog < 1.0

    @property
    def pose_label(self) -> str:
        return "MOVING" if self.pose_busy else self.pose

    def start_show(self, name: str, duration: float, now: float) -> None:
        if not self.frozen:
            self.show = name
            self.show_end = now + duration

    # ---------------------------------------------------------------- Schritt
    def step(self, dt: float, now: float) -> None:
        r = self.cfg.robot
        self.t = now
        if self.power_on:
            tau = r.motor_tau
            tgt_l = clamp(self.u_l, -1, 1) * r.v_free / r.wheel_radius
            tgt_r = clamp(self.u_r, -1, 1) * r.v_free / r.wheel_radius
        else:
            tau = r.brake_tau
            tgt_l = tgt_r = 0.0
        k = 1.0 - math.exp(-dt / tau)
        self.wl += (tgt_l - self.wl) * k
        self.wr += (tgt_r - self.wr) * k
        self.phi_l += self.wl * dt
        self.phi_r += self.wr * dt
        vl, vr = self.wl * self.r_l, self.wr * self.r_r
        self.v = (vl + vr) / 2.0
        self.w = (vr - vl) / self.track + self.rng.gauss(0, 0.004)
        mid = self.th + self.w * dt / 2
        self.x += self.v * math.cos(mid) * dt
        self.y += self.v * math.sin(mid) * dt
        self.th = wrap(self.th + self.w * dt)
        # Haltung
        if self.pose_prog < 1.0 and not self.frozen:
            self.pose_prog = min(1.0, self.pose_prog + dt / max(self.pose_dur, 1e-3))
            if self.pose_prog >= 1.0:
                self.pose = self.pose_to
        if self.show and now >= self.show_end:
            self.show = ""
        # Energie
        p = r.p_base_w
        p += r.p_motor_max_w * (abs(self.wl) + abs(self.wr)) * r.wheel_radius / (2 * r.v_free)
        p += r.p_servo_move_w if self.pose_busy else r.p_servo_hold_w
        self.energy_wh += p * dt / 3600.0
        self.power_w = p

    # ---------------------------------------------------------------- Sensoren (Rohwerte)
    def encoder_ticks(self) -> tuple[int, int]:
        k = self.cfg.robot.encoder_cpr / (2 * math.pi)
        return int(self.phi_l * k), int(self.phi_r * k)

    def gyro(self) -> float:
        return self.w + self.gyro_bias + self.rng.gauss(0, math.radians(self.cfg.robot.gyro_noise_dps))

    @property
    def soc(self) -> float:
        return max(0.0, 1.0 - self.energy_wh / self.cfg.robot.battery_wh)
