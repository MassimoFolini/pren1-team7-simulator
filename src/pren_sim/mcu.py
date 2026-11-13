"""Modell der Mikrocontroller-Firmware (Echtzeit-Teil von V2).

Aufgaben laut MS2-Bericht: Encoder, Regelung, Servos, Not-Aus-Ueberwachung. Der Mikrocontroller haelt
den Roboter auch bei Absturz des Rechners sicher an (Watchdog) und der Hardware-Not-Aus wirkt ohne den Rechner.
"""
from __future__ import annotations

import math

from . import protocol as P
from .config import Config
from .geometry import clamp, wrap
from .link import SimLink
from .plant import Plant

WATCHDOG_S = 0.5


class Mcu:
    def __init__(self, cfg: Config, plant: Plant, link: SimLink):
        self.cfg = cfg
        self.plant = plant
        self.link = link
        self.estop = False
        self.estop_src = ""
        self.hw_button = False        # Not-Aus-Taster gedrueckt (Hardware)
        self.v_cmd = 0.0
        self.w_cmd = 0.0
        self.v_set = 0.0              # nach Rampe
        self.w_set = 0.0
        self.last_cmd_t = -1e9
        self.wdg_fired = False
        # Odometrie-Schaetzung (Start = Startpose; Gyro-Heading, Encoder-Distanz)
        self.ox, self.oy, self.oth = 0.0, 0.0, math.pi
        self.ov, self.ow = 0.0, 0.0
        self._tl, self._tr = plant.encoder_ticks()
        self.i_l = self.i_r = 0.0
        self.wmeas_l = self.wmeas_r = 0.0
        self.taster = False
        self._touch_sent = False
        self._t_odom = 0.0
        self._t_slow = 0.0
        self.t = 0.0
        self.last_err = ""

    # ------------------------------------------------------------ Telegramme vom SBC
    def _rx(self, line: str, now: float) -> None:
        cmd, a = P.parse(line)
        if cmd == P.CMD_DRIVE and len(a) >= 2:
            if float(a[0]) == 0.0 and float(a[1]) == 0.0:
                self.v_cmd = self.w_cmd = 0.0
                self.last_cmd_t = now
            elif self.estop:
                self._err("ESTOP", "gesperrt")
            elif self.plant.pose != "STAND" or self.plant.pose_busy:
                self._err("POSE", "Fahren nur im Stand")
            else:
                self.v_cmd = clamp(float(a[0]), -self.cfg.robot.v_max, self.cfg.robot.v_max)
                self.w_cmd = clamp(float(a[1]), -self.cfg.robot.w_max, self.cfg.robot.w_max)
                self.last_cmd_t = now
                self.wdg_fired = False
        elif cmd == P.CMD_STOP:
            self.v_cmd = self.w_cmd = 0.0
        elif cmd == P.CMD_PING:
            self.link.mcu_send(P.MSG_PONG)        # PING haelt die Fahr-Ueberwachung bewusst NICHT wach (nur DRIVE)
        elif cmd == P.CMD_POSE and a:
            tgt = a[0].upper()
            if self.estop:
                self._err("ESTOP", "gesperrt")
            elif tgt not in P.POSES:
                self._err("ARG", tgt)
            elif abs(self.ov) > 0.03 or abs(self.ow) > 0.15:
                self._err("MOVING", "erst anhalten")
            else:
                self.plant.set_pose(tgt)
        elif cmd == P.CMD_SHOW and a:
            name = a[0].upper()
            dur = {"HAPPY": 2.5, "TAIL": 1.5, "SPIN": 1.0}.get(name, 1.0)
            self.plant.start_show(name, dur, now)
        elif cmd == P.CMD_ESTOP:
            self._latch("sw")
        elif cmd == P.CMD_ESTOP_RESET:
            if self.hw_button:
                self._err("ESTOP", "Taster noch gedrueckt")
            else:
                self.estop = False
                self.estop_src = ""
                self.plant.power_on = True
                self.plant.frozen = False
                self.link.mcu_send(f"{P.MSG_EVT} ESTOP_CLEARED")
        elif cmd == P.CMD_ODOM_RESET:
            self.ox, self.oy, self.oth = 0.0, 0.0, math.pi

    def _err(self, code: str, text: str = "") -> None:
        self.last_err = f"{code} {text}".strip()
        self.link.mcu_send(f"{P.MSG_ERR} {code} {text}".strip())

    def _latch(self, src: str) -> None:
        if not self.estop:
            self.estop = True
            self.estop_src = src
            self.v_cmd = self.w_cmd = self.v_set = self.w_set = 0.0
            self.plant.power_on = False
            self.plant.frozen = True
            self.link.mcu_send(f"{P.MSG_EVT} ESTOP {src}")

    # ------------------------------------------------------------ Hardware-Eingaenge
    def press_estop(self) -> None:
        self.hw_button = True
        self._latch("hw")             # wirkt ohne SBC und ohne Verbindung

    def release_estop(self) -> None:
        self.hw_button = False

    def press_start(self) -> None:
        self.link.mcu_send(f"{P.MSG_EVT} BTN_START")

    # ------------------------------------------------------------ Zyklus (100 Hz)
    def step(self, now: float, dt: float, taster_contact: bool) -> None:
        r = self.cfg.robot
        self.t = now
        for line in self.link.mcu_recv():
            try:
                self._rx(line, now)
            except (ValueError, IndexError):
                self._err("SYNTAX", line[:20])

        # Watchdog: Rechner meldet sich nicht mehr -> anhalten
        if (self.v_cmd or self.w_cmd) and now - self.last_cmd_t > WATCHDOG_S:
            self.v_cmd = self.w_cmd = 0.0
            if not self.wdg_fired:
                self.wdg_fired = True
                self.link.mcu_send(f"{P.MSG_EVT} WDG")

        # Rampe
        self.v_set += clamp(self.v_cmd - self.v_set, -r.accel * dt, r.accel * dt)
        self.w_set += clamp(self.w_cmd - self.w_set, -r.alpha * dt, r.alpha * dt)

        # Encoder -> Radgeschwindigkeit, Odometrie
        tl, tr = self.plant.encoder_ticks()
        m = 2 * math.pi / r.encoder_cpr
        dl, drr = (tl - self._tl) * m, (tr - self._tr) * m
        self._tl, self._tr = tl, tr
        self.wmeas_l += (dl / dt - self.wmeas_l) * 0.5
        self.wmeas_r += (drr / dt - self.wmeas_r) * 0.5
        ds = (dl + drr) * r.wheel_radius / 2.0
        gyro = self.plant.gyro()
        self.oth = wrap(self.oth + gyro * dt)
        self.ox += ds * math.cos(self.oth - gyro * dt / 2)
        self.oy += ds * math.sin(self.oth - gyro * dt / 2)
        self.ov = ds / dt
        self.ow = gyro

        # Radregler (PI + Vorsteuerung)
        if self.estop:
            self.plant.u_l = self.plant.u_r = 0.0
            self.i_l = self.i_r = 0.0
        else:
            vl_t = self.v_set - self.w_set * r.track / 2.0
            vr_t = self.v_set + self.w_set * r.track / 2.0
            el = vl_t - self.wmeas_l * r.wheel_radius
            er = vr_t - self.wmeas_r * r.wheel_radius
            self.i_l = clamp(self.i_l + el * dt * 2.5, -0.3, 0.3)
            self.i_r = clamp(self.i_r + er * dt * 2.5, -0.3, 0.3)
            self.plant.u_l = clamp(vl_t / r.v_free + 0.6 * el + self.i_l, -1, 1)
            self.plant.u_r = clamp(vr_t / r.v_free + 0.6 * er + self.i_r, -1, 1)

        # Taster / Kontakt (Fuehler an der Nase)
        if taster_contact and not self._touch_sent:
            self._touch_sent = True
            self.link.mcu_send(f"{P.MSG_EVT} TOUCH")
        if not taster_contact:
            self._touch_sent = False

        # Telemetrie
        if now - self._t_odom >= 0.05 - 1e-9:
            self._t_odom = now
            self.link.mcu_send(P.fmt_odom(self.ox, self.oy, self.oth, self.v_set, self.w_set))
            st = "BUSY" if self.plant.pose_busy else "DONE"
            self.link.mcu_send(f"{P.MSG_POSE} {self.plant.pose_label} {st}")
        if now - self._t_slow >= 0.5 - 1e-9:
            self._t_slow = now
            self.link.mcu_send(f"{P.MSG_BAT} {self.plant.soc:.3f} {self.plant.energy_wh:.3f}")
