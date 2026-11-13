"""Simulations-Engine: verbindet Strecke, Firmware-Modell, Spielfeld, Wahrnehmung und Brain.

Zeitraster: Physik + Firmware mit 100 Hz (sim.dt), Wahrnehmung + Brain mit 20 Hz (sim.brain_hz).
Alles deterministisch ueber den Seed (Reproduzierbarkeit fuer Tests).
"""
from __future__ import annotations

import math
import random

from . import brain as B
from .brain import Brain
from .config import Config
from .eventlog import EventLog
from .link import SimLink
from .mcu import Mcu
from .perception import GESTURES, SimSensors, WORDS
from .plant import Plant
from .world import World


class Simulation:
    def __init__(self, cfg: Config | None = None, seed: int | None = None):
        self.cfg = (cfg or Config()).copy()
        if seed is not None:
            self.cfg.sim.seed = seed
        self.seed = self.cfg.sim.seed
        self.rng = random.Random(self.seed)
        self.log = EventLog()
        self.link = SimLink(self.cfg.sim.link_latency_s)
        self.plant = Plant(self.cfg, self.rng)
        self.world = World(self.cfg, self.plant)
        self.world.set_referee_distance(self.cfg.env.referee_distance)
        self.mcu = Mcu(self.cfg, self.plant, self.link)
        self.sensors = SimSensors(self.cfg, self.rng, self.world)
        self.brain = Brain(self.cfg, self.link, self.log)
        self.t = 0.0
        self.n = 0
        self.paused = False
        self._brain_period = max(1, round(1.0 / (self.cfg.sim.brain_hz * self.cfg.sim.dt)))
        self.trail_true: list[tuple[float, float]] = []
        self.trail_odom: list[tuple[float, float]] = []
        self._last_state = self.brain.state
        self.truth_contact_t: float | None = None
        self.outside_s = 0.0
        self.max_outside = 0.0
        self._contact_prev = False
        self.estop_press_t: float | None = None
        self._estop_wait_stop = False
        self.run_energy0 = 0.0
        self.cmd_history: list[dict] = []
        self._entered_field = False
        self._n_complete = 0
        self.ref_say = ("", 0.0)
        self.ref_gesture = ("", 0.0)

    # ------------------------------------------------------------------ Eingriffe (Schiedsrichter / Bediener)
    def say(self, word: str) -> None:
        w = word.upper()
        self.sensors.mic.utter(w, self.t, self._ref_dist())
        self.ref_say = (w, self.t + 1.6)
        self.log.add(self.t, "REFEREE", "say", f"Schiedsrichter sagt «{w}» ({self._ref_dist():.1f} m)", word=w)

    def gesture(self, name: str) -> None:
        g = name.upper()
        self.sensors.gestures.perform(g, self.t, self._ref_dist())
        self.ref_gesture = (g, self.t + 2.9)
        self.log.add(self.t, "REFEREE", "gesture", f"Schiedsrichter zeigt Geste «{g}»", name=g)

    def say_live(self, word: str, conf: float, text: str = "") -> None:
        """Befehl aus dem echten Mikrofon des Bedieners (Browser-Spracherkennung)."""
        w = word.upper()
        self.sensors.mic.inject(w, max(0.0, min(1.0, conf)), self.t)
        self.ref_say = (w, self.t + 1.6)
        self.log.add(self.t, "REFEREE", "say_live", f"Mikrofon live: «{text or w}» -> {w} ({conf:.2f})", word=w, conf=round(conf, 2))

    def gesture_live(self, label: str | None, conf: float) -> None:
        """Ein Kamerabild der echten Webcam (Label oder None = keine Geste)."""
        label = label.upper() if label else None
        self.sensors.gestures.inject_live(label, max(0.0, min(1.0, conf)), self.t)
        if label:
            self.ref_gesture = (label, self.t + 0.6)

    def press_start(self) -> None:
        self.log.add(self.t, "REFEREE", "button", "Start-Taster gedrueckt")
        if self.cfg.env.touch_taster_ok:
            self.mcu.press_start()

    def press_estop(self) -> None:
        self.log.add(self.t, "REFEREE", "estop_press", "NOT-AUS gedrueckt")
        self.estop_press_t = self.t
        self._estop_wait_stop = True
        self.mcu.press_estop()

    def release_estop(self) -> None:
        self.mcu.release_estop()
        self.log.add(self.t, "REFEREE", "estop_release", "Not-Aus-Taster entriegelt")

    def reset_after_estop(self) -> None:
        self.brain.operator_reset = True
        self.log.add(self.t, "OPERATOR", "estop_reset", "Quittierung/Neustart nach Not-Aus")

    def set_env(self, **kw) -> None:
        env = self.cfg.env
        for k, v in kw.items():
            if not hasattr(env, k):
                raise KeyError(k)
            setattr(env, k, type(getattr(env, k))(v))
            if k == "referee_distance":
                self.world.set_referee_distance(float(v))
            if k == "link_ok":
                self.link.up = bool(v)
        self.log.add(self.t, "OPERATOR", "env", "Umgebung geaendert: " + ", ".join(f"{k}={v}" for k, v in kw.items()))

    def place_bone(self, x: float, y: float, th: float | None = None) -> None:
        self.world.place_bone(x, y, th)
        self.truth_contact_t = None
        self.log.add(self.t, "OPERATOR", "bone", f"Knochen platziert bei ({x:.2f} | {y:.2f}) m")

    def random_bone(self) -> None:
        b = self.world.random_bone(self.rng)
        self.truth_contact_t = None
        self.log.add(self.t, "OPERATOR", "bone", f"Knochen zufaellig platziert bei ({b.x:.2f} | {b.y:.2f}) m")

    def _ref_dist(self) -> float:
        return math.hypot(self.world.referee[0] - self.plant.x, self.world.referee[1] - self.plant.y)

    # ------------------------------------------------------------------ Takt
    def step(self) -> None:
        dt = self.cfg.sim.dt
        self.t = round(self.t + dt, 6)
        self.n += 1
        self.link.tick(self.t)

        contact = self.world.contact()
        self.mcu.step(self.t, dt, contact and self.cfg.env.touch_taster_ok)
        self.plant.step(dt, self.t)

        if self.n % self._brain_period == 0:
            fr = self.sensors.read(self.t)
            self.brain.tick(self.t, fr)
            self._observe()
            if self.n % (self._brain_period * 2) == 0:
                self.trail_true.append((round(self.plant.x, 3), round(self.plant.y, 3)))
                self.trail_odom.append((round(self.mcu.ox, 3), round(self.mcu.oy, 3)))
                if len(self.trail_true) > 1500:
                    del self.trail_true[:300]; del self.trail_odom[:300]

        # Wahrheits-Ereignisse (nur fuer die Auswertung)
        if contact and not self._contact_prev:
            self.truth_contact_t = self.t
            self.log.add(self.t, "WORLD", "contact_true", "Knochen wirklich beruehrt",
                         x=round(self.plant.x, 3), y=round(self.plant.y, 3))
        self._contact_prev = contact
        if self._estop_wait_stop and abs(self.plant.v) < 0.01 and abs(self.plant.w) < 0.05:
            self._estop_wait_stop = False
            self.log.add(self.t, "WORLD", "stopped", f"Roboter steht {self.t - (self.estop_press_t or 0):.2f} s nach Not-Aus",
                         stop_time=round(self.t - (self.estop_press_t or 0), 3))
        if self.brain.state in (B.SUCHEN, B.ANFAHREN, B.FUND, B.RUECKKEHR):
            ex = self.world.field_excess()
            if ex <= self.cfg.field.field_margin:
                self._entered_field = True
            elif self._entered_field:
                self.outside_s += dt
                self.max_outside = max(self.max_outside, ex)
        elif self.brain.state in (B.BEREIT, B.PLATZ):
            self._entered_field = False

    def _observe(self) -> None:
        rc = self.log.find("run_complete")
        if len(rc) > self._n_complete:
            self._n_complete = len(rc)
            p = self.plant
            self.log.add(self.t, "WORLD", "run_truth", "Endlage (Wahrheit)", x=round(p.x, 3), y=round(p.y, 3),
                         th=round(p.th, 3), pose=p.pose, in_start_field=self.world.in_start_field())
        if self.brain.state != self._last_state:
            if self.brain.state == B.DREHEN:
                self.run_energy0 = self.plant.energy_wh
            self._last_state = self.brain.state

    def run_for(self, seconds: float) -> None:
        end = self.t + seconds
        while self.t < end - 1e-9:
            self.step()

    def run_until(self, cond, max_s: float) -> bool:
        end = self.t + max_s
        while self.t < end:
            self.step()
            if cond(self):
                return True
        return False

    def wait_ready(self, max_s: float = 10.0) -> bool:
        return self.run_until(lambda s: s.brain.state == B.BEREIT, max_s)

    # ------------------------------------------------------------------ Momentaufnahme fuer die Oberflaeche
    def snapshot(self, last_event_id: int = 0) -> dict:
        p, w, b, m = self.plant, self.world, self.brain, self.mcu
        bone = w.bone
        bearing, dist = w.bone_view()
        f = b.frame
        return {
            "t": round(self.t, 2),
            "paused": self.paused,
            "seed": self.seed,
            "robot": {"x": round(p.x, 4), "y": round(p.y, 4), "th": round(p.th, 4), "v": round(p.v, 3), "w": round(p.w, 3),
                      "wl": round(p.wl, 2), "wr": round(p.wr, 2), "phi_l": round(p.phi_l, 3), "phi_r": round(p.phi_r, 3),
                      "pose": p.pose_label, "pose_to": p.pose_to, "pose_prog": round(p.pose_prog, 2),
                      "show": p.show, "power_on": p.power_on},
            "odom": {"x": round(m.ox, 4), "y": round(m.oy, 4), "th": round(m.oth, 4)},
            "bone": {"x": round(bone.x, 3), "y": round(bone.y, 3), "th": round(bone.th, 3),
                     "bearing": round(bearing, 3), "dist": round(dist, 3), "in_sector": w.bone_in_sector()},
            "referee": {"x": w.referee[0], "y": w.referee[1],
                        "say": self.ref_say[0] if self.t < self.ref_say[1] else "",
                        "gesture": self.ref_gesture[0] if self.t < self.ref_gesture[1] else ""},
            "live_gesture": (lambda lv: None if lv is None else {"label": lv[0], "conf": round(lv[1], 2)})(self.sensors.gestures.live_state(self.t)),
            "tof": None if f is None or f.tof is None else round(f.tof, 3),
            "detect": None if (f is None or f.bone is None) else {"bearing": round(f.bone.bearing, 3), "dist": round(f.bone.dist, 3),
                                                                  "conf": round(f.bone.conf, 2)},
            "target": None if not b.target else {"x": round(b.target["x"], 3), "y": round(b.target["y"], 3),
                                                  "conf": round(b.target["conf"], 2)},
            "brain": {"state": b.state, **b.status(), "pose": b.mcu_pose, "output": b.output,
                      "heard": {"word": b.last_heard[0], "conf": round(b.last_heard[1], 2)}},
            "mcu": {"estop": m.estop, "estop_src": m.estop_src, "hw_button": m.hw_button, "v_set": round(m.v_set, 3),
                    "w_set": round(m.w_set, 3), "u_l": round(p.u_l, 2), "u_r": round(p.u_r, 2),
                    "link_up": self.link.up, "tx": self.link.tx_count, "rx": self.link.rx_count},
            "battery": {"soc": round(p.soc, 3), "wh": round(p.energy_wh, 3), "power_w": round(getattr(p, "power_w", 0.0), 1)},
            "env": self.cfg.env.__dict__.copy(),
            "field": {"start_l": self.cfg.field.start_field_l, "start_w": self.cfg.field.start_field_w,
                      "angle": self.cfg.field.sector_angle_deg, "radius": self.cfg.field.sector_radius,
                      "axis": self.cfg.field.sector_axis_deg, "interaction": self.cfg.field.interaction_radius,
                      "bone_l": self.cfg.field.bone_length, "bone_w": self.cfg.field.bone_width},
            "robot_dim": {"length": self.cfg.robot.length, "width": self.cfg.robot.width, "track": self.cfg.robot.track,
                          "wheel_r": self.cfg.robot.wheel_radius, "fov": self.cfg.robot.camera_fov_deg,
                          "nose": self.cfg.robot.nose_offset},
            "trail_true": self.trail_true[-600:],
            "trail_odom": self.trail_odom[-600:],
            "outside_s": round(self.outside_s, 2),
            "events": self.log.since(last_event_id)[-150:],
        }
