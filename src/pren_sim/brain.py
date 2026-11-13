"""Brain = Software des Einplatinenrechners (Raspberry Pi 5) in Variante V2.

Entspricht dem Blockschaltbild Software (Ebenen 3-4) und dem Zustandsdiagramm:
Befehls-Arbitration (Sprache + Geste + Taster), Zustandsautomat/Verhalten, Suchstrategie,
Quittierungs-Modul. Alles Zeitkritische (Regelung, Not-Aus) liegt im Mikrocontroller (mcu.py).

Das Brain kennt weder die wahre Pose noch den Simulator: es sieht nur einen SensorFrame (perception.py)
und die Telegramme des Mikrocontrollers (protocol.py).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from . import protocol as P
from .config import Config
from .eventlog import EventLog
from .geometry import clamp, sector_excess, wrap
from .frames import GESTURES, WORDS, SensorFrame

# ---- Zustaende (Zustandsdiagramm_PREN1) ------------------------------------
INIT, BEREIT, PLATZ, HIER, DREHEN, SUCHEN = "INIT", "BEREIT", "PLATZ", "HIER", "DREHEN", "SUCHEN"
ANFAHREN, FUND, RUECKKEHR, KUNST, NOT_AUS = "ANFAHREN", "FUND_MELDEN", "RUECKKEHR", "KUNSTSTUECK", "NOT_AUS"

STATES = (INIT, BEREIT, PLATZ, HIER, DREHEN, SUCHEN, ANFAHREN, FUND, RUECKKEHR, KUNST, NOT_AUS)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    INIT: (BEREIT, NOT_AUS),
    BEREIT: (PLATZ, HIER, DREHEN, KUNST, NOT_AUS),
    PLATZ: (BEREIT, NOT_AUS),
    HIER: (BEREIT, NOT_AUS),
    DREHEN: (SUCHEN, RUECKKEHR, NOT_AUS),
    SUCHEN: (ANFAHREN, FUND, RUECKKEHR, NOT_AUS),
    ANFAHREN: (FUND, SUCHEN, RUECKKEHR, NOT_AUS),
    FUND: (RUECKKEHR, NOT_AUS),
    RUECKKEHR: (BEREIT, NOT_AUS),
    KUNST: (BEREIT, NOT_AUS),
    NOT_AUS: (BEREIT,),
}

MOVING_STATES = (HIER, DREHEN, SUCHEN, ANFAHREN, RUECKKEHR, KUNST)


@dataclass
class Cmd:
    source: str      # voice | gesture | taster
    name: str        # HIER | BRAV | SITZ | SUCH | PLATZ | AUF | <Zusatzbefehl>
    conf: float


def vote_gesture(frames, conf_thr: float, votes_needed: int):
    """Mehrheitsfilter ueber die letzten Bilder: mindestens `votes_needed` Treffer derselben Geste mit Konfidenz >= conf_thr."""
    votes: dict[str, list[float]] = {}
    for g in frames:
        if g and g[1] >= conf_thr and g[0] in GESTURES:
            votes.setdefault(g[0], []).append(g[1])
    best = None
    for name, confs in votes.items():
        if len(confs) >= votes_needed and (best is None or len(confs) > best[2]):
            best = (name, sum(confs) / len(confs), len(confs))
    return None if best is None else (best[0], best[1])


class Brain:
    def __init__(self, cfg: Config, link, log: EventLog):
        self.cfg, self.bc = cfg, cfg.brain
        self.link, self.log = link, log
        self.state = INIT
        self.t = 0.0
        self.t_state = 0.0
        # Telemetrie vom Mikrocontroller
        self.odom = (0.0, 0.0, math.pi, 0.0, 0.0)
        self.odom_t = -1e9
        self.mcu_pose = "STAND"
        self.mcu_pose_busy = False
        self.estop = False
        self.soc = 1.0
        self.energy_wh = 0.0
        self.start_pose = (0.0, 0.0, math.pi)
        # Befehle
        self.gbuf: deque = deque(maxlen=self.bc.gesture_window)
        self.t_last_cmd = -1e9
        self.last_cmd: Cmd | None = None
        self.last_heard = ("", 0.0)
        self.btn = False
        self.touch = False
        self.touch_t = 0.0
        self.operator_reset = False
        # Verhalten
        self.frame: SensorFrame | None = None
        self._drive: tuple[float, float] | None = None
        self._moving = False
        self._t_ping = 0.0
        self.t_search0 = 0.0
        self.search_idx = 0
        self.search_dir = 1
        self.bone_hits: deque = deque()
        self.target: dict | None = None
        self.ret_phase = ""
        self.ret_reason = ""
        self.fault = ""
        self.output = {"sound": "", "led": "", "eyes": "neutral", "t": -1.0}
        self.confidence = 0.0
        self.sub = ""
        self._turn_acc = 0.0
        self._turn_last = 0.0
        self._here0 = (0.0, 0.0)
        self._trick_t0 = 0.0
        self._prev_pose_state = ("STAND", False)
        self.found_t = None
        self._init_sent = False
        self._joy_t = 0.0
        self._t_phase = 0.0
        self._g_lock = False
        self._t_reset = -1e9
        self._g_quiet = 0

    # =================================================================== Hilfen
    @property
    def pose_ready(self) -> bool:
        return not self.mcu_pose_busy

    def goto(self, new: str, reason: str = "") -> None:
        if new != self.state and new not in TRANSITIONS[self.state]:
            self.log.add(self.t, "SBC", "warn", f"unzulaessiger Uebergang {self.state} -> {new}")
        self.log.add(self.t, "SBC", "state", f"{self.state} -> {new}" + (f" ({reason})" if reason else ""),
                     frm=self.state, to=new, reason=reason)
        self.state = new
        self.t_state = self.t
        self.sub = ""

    def drive(self, v: float, w: float) -> None:
        self._drive = (v, w)

    def send(self, line: str) -> None:
        self.link.sbc_send(line)

    def ack(self, cmd: str, source: str, conf: float, sound: str, led: str, eyes: str) -> None:
        self.output = {"sound": sound, "led": led, "eyes": eyes, "t": self.t}
        self.log.add(self.t, "SBC", "ack", f"Quittierung {cmd}: {sound} / LED {led} / Augen {eyes}",
                     cmd=cmd, source=source, conf=round(conf, 2))

    @property
    def axis(self) -> float:
        """Achse des Suchbereichs = Startrichtung + 180 Grad (Hund startet mit Kopf weg vom Suchfeld)."""
        return wrap(self.start_pose[2] + math.pi)

    def nav_to(self, tx: float, ty: float, vmax: float, tol: float) -> bool:
        ox, oy, th = self.odom[0], self.odom[1], self.odom[2]
        dx, dy = tx - ox, ty - oy
        d = math.hypot(dx, dy)
        if d < tol:
            return True
        err = wrap(math.atan2(dy, dx) - th)
        w = clamp(2.6 * err, -1.8, 1.8)
        if abs(err) > math.radians(35):
            v = 0.0
            w = math.copysign(max(abs(w), 0.5), w)
        else:
            v = min(vmax, 0.7 * d + 0.06) * max(0.2, math.cos(err))
        self.drive(v, w)
        return False

    def turn_to(self, heading: float, tol_deg: float | None = None) -> bool:
        err = wrap(heading - self.odom[2])
        tol = math.radians(self.bc.heading_tol_deg if tol_deg is None else tol_deg)
        if abs(err) <= tol:
            self.drive(0.0, 0.0)
            return True
        w = clamp(2.2 * err, -1.8, 1.8)
        self.drive(0.0, math.copysign(max(abs(w), 0.35), w))
        return False

    def pose_cmd(self, name: str) -> None:
        self.send(f"{P.CMD_POSE} {name}")

    def stood(self) -> bool:
        return self.mcu_pose == "STAND" and self.pose_ready

    # =================================================================== Eingang
    def _ingest(self) -> None:
        for line in self.link.sbc_recv():
            cmd, a = P.parse(line)
            try:
                if cmd == P.MSG_ODOM and len(a) >= 5:
                    self.odom = tuple(float(x) for x in a[:5])
                    self.odom_t = self.t
                elif cmd == P.MSG_POSE and len(a) >= 2:
                    self.mcu_pose, self.mcu_pose_busy = a[0], a[1] == "BUSY"
                    cur = (self.mcu_pose, self.mcu_pose_busy)
                    if self._prev_pose_state[1] and not cur[1] and cur[0] in P.POSES:
                        self.log.add(self.t, "MCU", "pose_done", f"Haltung erreicht: {cur[0]}", pose=cur[0])
                    self._prev_pose_state = cur
                elif cmd == P.MSG_BAT and len(a) >= 2:
                    self.soc, self.energy_wh = float(a[0]), float(a[1])
                elif cmd == P.MSG_EVT and a:
                    e = a[0]
                    if e == "TOUCH":
                        self.touch, self.touch_t = True, self.t
                        self.log.add(self.t, "MCU", "touch", "Kontakt am Fuehler gemeldet")
                    elif e == "ESTOP":
                        self.estop = True
                        self.log.add(self.t, "MCU", "estop", f"Not-Aus ausgeloest ({a[1] if len(a) > 1 else '?'})")
                    elif e == "ESTOP_CLEARED":
                        self.estop = False
                        self.log.add(self.t, "MCU", "estop_cleared", "Not-Aus quittiert")
                    elif e == "BTN_START":
                        self.btn = True
                    elif e == "WDG":
                        self.log.add(self.t, "MCU", "watchdog", "Watchdog: Rechner antwortet nicht, Raeder gestoppt")
                elif cmd == P.MSG_ERR:
                    self.log.add(self.t, "MCU", "err", "Fehler vom MCU: " + " ".join(a))
            except (ValueError, IndexError):
                self.log.add(self.t, "SBC", "warn", f"Telegramm nicht lesbar: {line[:30]}")

    # =================================================================== Arbitration
    def _arbitrate(self, fr: SensorFrame) -> Cmd | None:
        bc = self.bc
        cmd: Cmd | None = None
        extra = bc.extra_command_word
        for kw in fr.keywords:
            self.last_heard = (kw.word, kw.conf)
            if kw.conf >= bc.cmd_conf and (kw.word in WORDS or kw.word == extra):
                cmd = cmd or Cmd("voice", kw.word, kw.conf)
            else:
                self.log.add(self.t, "SBC", "reject", f"Sprache verworfen: {kw.word} ({kw.conf:.2f})",
                             word=kw.word, conf=round(kw.conf, 2))
        self.gbuf.append(fr.gesture)
        if self._g_lock:
            # nach einem akzeptierten Befehl dieselbe Geste nicht noch einmal auswerten, bis die Hand weg ist
            self._g_quiet = self._g_quiet + 1 if fr.gesture is None else 0
            if self._g_quiet >= 10:
                self._g_lock = False
                self.gbuf.clear()
        else:
            g = vote_gesture(self.gbuf, bc.gesture_conf, bc.gesture_votes)
            if g:
                cmd = cmd or Cmd("gesture", g[0], g[1])
        if self.btn:
            self.btn = False
            if bc.use_taster_fallback:
                cmd = cmd or Cmd("taster", "SUCH", 1.0)
        if cmd and self.t - self.t_last_cmd < bc.cooldown_s and cmd.source != "taster":
            return None
        return cmd

    def _accept(self, c: Cmd) -> None:
        self.t_last_cmd = self.t
        self.last_cmd = c
        self.gbuf.clear()
        if c.source == "gesture":
            self._g_lock, self._g_quiet = True, 0
        self.confidence = c.conf
        self.log.add(self.t, "SBC", "cmd", f"Befehl erkannt: {c.name} ({c.source}, {c.conf:.2f})",
                     name=c.name, source=c.source, conf=round(c.conf, 2))

    def _dispatch(self, c: Cmd) -> None:
        s, n = self.state, c.name
        extra = self.bc.extra_command_word
        if s == BEREIT:
            if n == "HIER" and c.source == "voice":
                self._accept(c); self.ack(n, c.source, c.conf, "Bellen kurz", "gruen blinkt", "aufmerksam")
                self._here0 = (self.odom[0], self.odom[1])
                if not self.stood():
                    self.pose_cmd("STAND")
                self.goto(HIER, "Sprache HIER")
            elif n == "BRAV" and c.source == "voice":
                self._accept(c); self.ack(n, c.source, c.conf, "Freudenlaut", "Regenbogen", "gluecklich")
                self.send(f"{P.CMD_SHOW} HAPPY")
            elif n == "SITZ":
                self._accept(c); self.ack(n, c.source, c.conf, "Ton tief", "gelb", "neutral")
                self.pose_cmd("SITZ")
            elif n == "PLATZ" and c.source == "gesture":
                self._accept(c); self.ack(n, c.source, c.conf, "Ton tief", "blau", "muede")
                self.pose_cmd("PLATZ")
                self.goto(PLATZ, "Geste PLATZ")
            elif n == "AUF" and c.source == "gesture":
                self._accept(c); self.ack(n, c.source, c.conf, "Ton hoch", "weiss", "wach")
                self.pose_cmd("STAND")
            elif n == "SUCH":
                self._accept(c); self.ack(n, c.source, c.conf, "Bellen", "orange", "fokussiert")
                self.t_search0 = self.t
                self.search_idx, self.search_dir = 0, 1
                self.bone_hits.clear(); self.target = None
                self.log.add(self.t, "SBC", "search_start", f"Suche gestartet ({c.source})", source=c.source)
                self.goto(DREHEN, "SUCH" if c.source == "voice" else "Taster")
            elif n == extra and c.source == "voice":
                self._accept(c); self.ack(n, c.source, c.conf, "Jubeln", "bunt", "zwinkern")
                self._turn_acc, self._turn_last, self._trick_t0 = 0.0, self.odom[2], self.t
                self.log.add(self.t, "SBC", "trick_start", "Kunststueck gestartet (PLATZHALTER)")
                self.goto(KUNST, "Zusatzbefehl")
            else:
                self.log.add(self.t, "SBC", "ignored", f"{n} ({c.source}) in {s} nicht vorgesehen")
        elif s == PLATZ:
            if n in ("AUF", "SITZ"):
                self._accept(c); self.ack(n, c.source, c.conf, "Ton hoch" if n == "AUF" else "Ton tief",
                                          "weiss" if n == "AUF" else "gelb", "wach")
                self.pose_cmd("STAND" if n == "AUF" else "SITZ")
                self.goto(BEREIT, f"{c.source} {n}")
            else:
                self.log.add(self.t, "SBC", "ignored", f"{n} ({c.source}) in PLATZ nicht vorgesehen")
        else:
            self.log.add(self.t, "SBC", "ignored", f"{n} ({c.source}) waehrend {s} ignoriert")

    # =================================================================== Zustaende
    def _bone_update(self, fr: SensorFrame) -> None:
        d = fr.bone
        while self.bone_hits and self.t - self.bone_hits[0][0] > self.bc.bone_confirm_window:
            self.bone_hits.popleft()
        if d and d.conf >= self.bc.bone_conf:
            tg = self._target_from(d)
            if self._outside_field(tg["x"], tg["y"]):
                self.log.add(self.t, "SBC", "reject", "Detektion ausserhalb des Suchbereichs verworfen",
                             x=round(tg["x"], 2), y=round(tg["y"], 2))
                return
            self.bone_hits.append((self.t, d))
            self.confidence = d.conf

    def _outside_field(self, x: float, y: float, margin: float = 0.5) -> bool:
        """Schaetzposition (Odometrie-Koordinaten) liegt deutlich ausserhalb des 30-Grad-Segments (Suchbereich)?"""
        f = self.cfg.field
        return sector_excess(x - self.start_pose[0], y - self.start_pose[1], self.cfg.sector_half,
                             f.sector_radius, self.axis) > margin

    def _target_from(self, d) -> dict:
        ox, oy, th = self.odom[0], self.odom[1], self.odom[2]
        ang = th + d.bearing
        return {"bearing": d.bearing, "dist": d.dist, "conf": d.conf, "t": self.t,
                "x": ox + d.dist * math.cos(ang), "y": oy + d.dist * math.sin(ang)}

    def _timeout(self) -> bool:
        return self.t - self.t_search0 > self.bc.search_timeout_s

    def _st_init(self, fr):
        if self.t - self.t_state >= self.bc.startup_s and self.t - self.odom_t < 0.3:
            self.start_pose = self.odom[:3]
            self.log.add(self.t, "SBC", "startup_ready", f"Startklar nach {self.t:.1f} s (Selbsttest ok)", t_ready=self.t)
            self.goto(BEREIT, "Selbsttest ok")

    def _st_here(self, fr):
        x0, y0 = self._here0
        travelled = math.hypot(self.odom[0] - x0, self.odom[1] - y0)
        if not self.stood():
            self.drive(0.0, 0.0)
            return
        near = fr.tof is not None and fr.tof <= self.bc.here_stop_distance
        if near or travelled >= self.bc.here_max_travel or self.t - self.t_state > 9.0:
            self.drive(0.0, 0.0)
            if abs(self.odom[3]) < 0.03:
                self.log.add(self.t, "SBC", "here_done", f"HIER: {travelled:.2f} m auf die Person zu gefahren",
                             travelled=round(travelled, 3))
                self.goto(BEREIT, "am Ziel")
        else:
            self.drive(self.bc.cruise_speed * 0.8, 0.0)

    def _st_drehen(self, fr):
        if self._timeout():
            self.ret_reason = "timeout"; self.goto(RUECKKEHR, "Timeout 2 min"); return
        if not self.stood():
            if self.sub != "stand":
                self.sub = "stand"; self.pose_cmd("STAND")
            self.drive(0.0, 0.0)
            return
        if self.turn_to(self.axis):
            self.log.add(self.t, "SBC", "turn_done", "Ausrichtung auf Suchbereich abgeschlossen")
            self.goto(SUCHEN, "Rücken -> Feld")

    def _search_waypoint(self):
        ax = self.axis
        s = (1.0, 2.0, 3.0, 4.0, self.cfg.field.sector_radius - 0.35)[self.search_idx]
        return s * math.cos(ax), s * math.sin(ax)

    def _st_suchen(self, fr):
        if self.touch or fr.touch_cam:
            return self._on_touch()
        if self._timeout():
            self.ret_reason = "timeout"; self.goto(RUECKKEHR, "Timeout 2 min"); return
        if len(self.bone_hits) >= self.bc.bone_confirm:
            self.target = self._target_from(self.bone_hits[-1][1])
            self.log.add(self.t, "SBC", "bone_seen", f"Knochen erkannt ({self.target['dist']:.2f} m, {self.target['conf']:.2f})",
                         dist=round(self.target["dist"], 2), conf=round(self.target["conf"], 2))
            self.goto(ANFAHREN, "Knochen erkannt"); return
        wx, wy = self._search_waypoint()
        if self.nav_to(wx, wy, self.bc.search_speed, 0.12):
            n = 5
            self.search_idx += self.search_dir
            if self.search_idx >= n:
                self.search_idx, self.search_dir = n - 2, -1
            elif self.search_idx < 0:
                self.search_idx, self.search_dir = 1, 1

    def _st_anfahren(self, fr):
        if self.touch or fr.touch_cam:
            return self._on_touch()
        if self._timeout():
            self.ret_reason = "timeout"; self.goto(RUECKKEHR, "Timeout 2 min"); return
        d = fr.bone
        if d and d.conf >= self.bc.bone_conf:
            self.target = self._target_from(d)
            self.confidence = d.conf
        tg = self.target
        if not tg:
            self.goto(SUCHEN, "Ziel verloren"); return
        age = self.t - tg["t"]
        blind = tg["dist"] < 0.55
        if (not blind and age > 1.5) or (blind and age > 3.0):
            self.log.add(self.t, "SBC", "target_lost", "Ziel verloren, Suche wird fortgesetzt")
            self.target = None; self.bone_hits.clear()
            self.goto(SUCHEN, "Ziel verloren"); return
        if blind:
            # Knochen unter dem Bildfeld: geradeaus weiter, Distanzsensor/Fuehler uebernehmen
            self.drive(0.12, 0.0)
        else:
            w = clamp(2.2 * tg["bearing"], -1.2, 1.2)
            if abs(tg["bearing"]) > math.radians(12):
                self.drive(0.0, w)
            else:
                v = clamp(0.5 * (tg["dist"] - 0.25), 0.10, self.bc.approach_speed)
                self.drive(v, w)

    def _on_touch(self) -> None:
        self.found_t = self.t
        self.drive(0.0, 0.0)
        self.send(f"{P.CMD_DRIVE} 0 0")
        self.ack("FUND", "sensor", 1.0, "Bellen laut", "gruen leuchtet", "gluecklich")
        self.send(f"{P.CMD_SHOW} HAPPY")
        self.log.add(self.t, "SBC", "found", "Fund gemeldet (am Ort der Beruehrung)")
        self.touch = False
        self.goto(FUND, "beruehrt")

    def _st_fund(self, fr):
        self.drive(0.0, 0.0)
        if self.t - self.t_state >= self.bc.found_hold_s:
            self.ret_reason = "found"
            self.goto(RUECKKEHR, "Fund gemeldet")

    def _st_rueckkehr(self, fr):
        if not self.ret_phase:
            self.ret_phase = "go"
        if self.ret_phase == "go":
            if self.nav_to(self.start_pose[0], self.start_pose[1], self.bc.cruise_speed, self.bc.return_tol):
                self.ret_phase = "align"
        elif self.ret_phase == "align":
            if self.turn_to(self.start_pose[2]):
                self.ret_phase = "settle"
                self._t_phase = self.t
        elif self.ret_phase == "settle":
            self.drive(0.0, 0.0)
            if self.t - self._t_phase >= 0.4 and abs(self.odom[3]) < 0.02:
                self.ret_phase = "sit"
                self._t_phase = self.t
                self.pose_cmd("SITZ")
        elif self.ret_phase == "sit":
            self.drive(0.0, 0.0)
            if self.mcu_pose == "SITZ" and self.pose_ready:
                self.log.add(self.t, "SBC", "run_complete", "Zurueck im Startfeld, sitzend",
                             reason=self.ret_reason, search_time=round(self.t - self.t_search0, 2))
                self.ret_phase = ""
                self.touch = False
                self.target = None
                self.bone_hits.clear()
                self.goto(BEREIT, "im Startfeld: sitzen")
            elif self.pose_ready and self.t - self._t_phase > 0.8:
                self._t_phase = self.t
                self.pose_cmd("SITZ")          # Befehl wiederholen (z. B. MCU war noch in Bewegung)

    def _st_kunst(self, fr):
        """PLATZHALTER-Kunststueck (Zusatzbefehl ist noch nicht definiert): Drehung 360 Grad, dann Freude."""
        if not self.stood():
            if self.sub != "stand":
                self.sub = "stand"; self.pose_cmd("STAND")
            self.drive(0.0, 0.0)
            return
        th = self.odom[2]
        if self.sub in ("", "stand"):
            self.sub = "spin"; self._turn_last = th; self._turn_acc = 0.0
            self.send(f"{P.CMD_SHOW} SPIN")
        if self.sub == "spin":
            self._turn_acc += wrap(th - self._turn_last)
            self._turn_last = th
            self.drive(0.0, 1.4)
            if abs(self._turn_acc) >= 2 * math.pi - 0.1 or self.t - self._trick_t0 > self.bc.trick_max_s:
                self.sub = "joy"; self.drive(0.0, 0.0)
                self.send(f"{P.CMD_SHOW} HAPPY"); self._joy_t = self.t
        elif self.sub == "joy":
            self.drive(0.0, 0.0)
            if self.t - self._joy_t > 2.5:
                self.log.add(self.t, "SBC", "trick_done", f"Kunststueck beendet nach {self.t - self._trick_t0:.1f} s",
                             duration=round(self.t - self._trick_t0, 2))
                self.goto(BEREIT, "Kunststueck fertig")

    def _st_notaus(self, fr):
        self.drive(0.0, 0.0)
        if self.operator_reset and self.fault != "LINK" and self.t - self._t_reset >= 0.5:
            self._t_reset = self.t
            self.send(P.CMD_ESTOP_RESET)
        if self.fault == "LINK" and self.t - self.odom_t < 0.3 and not self.estop:
            self.fault = ""
            self.goto(BEREIT, "Verbindung wieder da")
        elif not self.estop and self.fault == "" and self.operator_reset:
            self.operator_reset = False
            self.ret_phase = ""
            self.goto(BEREIT, "Not-Aus quittiert")

    # =================================================================== Zyklus
    def tick(self, now: float, fr: SensorFrame) -> None:
        self.t = now
        self.frame = fr
        self._drive = None
        self._ingest()
        if not self._init_sent:
            self._init_sent = True
            self.send(P.CMD_ODOM_RESET)
        self._bone_update(fr)

        # Sicherheit zuerst
        if self.state != NOT_AUS:
            if self.estop:
                self.fault = ""
                self.ret_phase = ""
                self.log.add(self.t, "SBC", "abort", f"Ablauf abgebrochen in {self.state} (Not-Aus)")
                self.goto(NOT_AUS, "Not-Aus")
            elif self.state != INIT and self.t - self.odom_t > self.bc.link_timeout_s:
                self.fault = "LINK"
                self.ret_phase = ""
                self.log.add(self.t, "SBC", "fault", "Verbindung zum Mikrocontroller verloren")
                self.goto(NOT_AUS, "Link verloren")

        # Befehle
        if self.state in (BEREIT, PLATZ):
            c = self._arbitrate(fr)
            if c:
                self._dispatch(c)
        else:
            # Eingaben verwerfen, damit nichts liegen bleibt
            self.gbuf.append(None)
            self.btn = False if self.state != INIT else self.btn

        {INIT: self._st_init, HIER: self._st_here, DREHEN: self._st_drehen, SUCHEN: self._st_suchen,
         ANFAHREN: self._st_anfahren, FUND: self._st_fund, RUECKKEHR: self._st_rueckkehr,
         KUNST: self._st_kunst, NOT_AUS: self._st_notaus,
         BEREIT: lambda f: None, PLATZ: lambda f: None}[self.state](fr)

        if self.state not in (SUCHEN, ANFAHREN):
            self.touch = False if self.state != FUND else self.touch

        # Ausgabe an MCU
        if self._drive is not None:
            self.send(P.fmt_drive(*self._drive))
            self._moving = abs(self._drive[0]) > 1e-6 or abs(self._drive[1]) > 1e-6
        elif self._moving:
            self.send(f"{P.CMD_DRIVE} 0 0")
            self._moving = False
        if not self._moving and self.t - self._t_ping >= 0.25:
            self._t_ping = self.t
            self.send(P.CMD_PING)

    # =================================================================== Status (Folie 8 der Aufgabenstellung)
    def status(self) -> dict:
        tg = self.target
        return {
            "command": self.last_cmd.name if self.last_cmd else "-",
            "robot_state": self.state,
            "target": "found" if (tg or self.state in (FUND, RUECKKEHR) and self.ret_reason == "found") else "not found",
            "confidence": round(self.confidence, 2),
            "sub": self.sub or self.ret_phase,
            "fault": self.fault,
        }
