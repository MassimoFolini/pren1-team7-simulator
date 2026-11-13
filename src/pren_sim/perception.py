"""Simulierte Wahrnehmung: Mikrofon/Schluesselworterkennung, Gesten, Knochen, Distanz, Beruehrung.

Die Modelle sind bewusst einfach und parametrisch (siehe docs/ANNAHMEN.md). Sie bilden die Eigenschaften
ab, die fuer die Software-Tests relevant sind: Fehlerraten abhaengig von Laerm, Licht und Distanz,
Latenz, Fehlklassifikationen und Fehlausloesungen. Spaeter ersetzen echte Erkennungen (Vosk, MediaPipe,
Objektdetektor) diese Klassen ueber dieselbe Schnittstelle (SensorFrame, siehe hal.py).
"""
from __future__ import annotations

import math
import random

from .config import Config
from .frames import GESTURES, WORDS, Detection, KeywordEvent, SensorFrame  # noqa: F401  (Re-Export)
from .world import World


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def light_factor(lux: float) -> float:
    """0.05..1: Bildqualitaet in Abhaengigkeit vom Licht (1 bei >= ca. 300 lx)."""
    return max(0.05, min(1.0, 0.25 + 0.75 * (math.log10(max(lux, 1.0)) - 1.0) / 1.5))


# ====================================================================== Sprache
class KeywordSpotter:
    """Schluesselworterkennung mit begrenztem Wortschatz (HIER, BRAV, SITZ, SUCH + [unk])."""

    def __init__(self, cfg: Config, rng: random.Random):
        self.cfg, self.rng = cfg, rng
        self._pending: list[tuple[float, str, float]] = []   # (ready_t, wort, distanz)
        self._last_false = 0.0

    def vocab(self) -> tuple:
        return WORDS + (self.cfg.brain.extra_command_word,)

    def speech_snr(self, distance: float, noise_db: float | None = None) -> float:
        env = self.cfg.env
        level = env.speech_level_db_1m - 20.0 * math.log10(max(distance, 0.1))
        return level - (env.noise_db if noise_db is None else noise_db)

    def p_correct(self, distance: float, noise_db: float | None = None) -> float:
        return _sigmoid((self.speech_snr(distance, noise_db) - 3.0) / 3.5)

    def utter(self, word: str, now: float, distance: float) -> None:
        # Aussprache ca. 0.6 s + Verarbeitung ca. 0.2-0.35 s
        self._pending.append((now + 0.6 + self.rng.uniform(0.2, 0.35), word, distance))

    def classify(self, word: str, distance: float, noise_db: float | None = None, t: float = 0.0) -> KeywordEvent | None:
        p = self.p_correct(distance, noise_db)
        if self.rng.random() < p:
            return KeywordEvent(word, min(0.99, max(0.35, 0.55 + 0.45 * p + self.rng.gauss(0, 0.06))), t, word)
        u = self.rng.random()
        if u < 0.55:                                   # nichts erkannt
            return None
        if u < 0.80:                                   # [unk]
            return KeywordEvent("[unk]", self.rng.uniform(0.3, 0.7), t, word)
        other = self.rng.choice([w for w in self.vocab() if w != word])   # Verwechslung
        return KeywordEvent(other, self.rng.uniform(0.35, 0.78), t, word)

    def read(self, now: float) -> list:
        out = []
        env = self.cfg.env
        if not env.mic_ok:
            self._pending.clear()
            return out
        keep = []
        for ready, word, dist in self._pending:
            if ready <= now:
                ev = self.classify(word, dist, None, now)
                if ev:
                    out.append(ev)
            else:
                keep.append((ready, word, dist))
        self._pending = keep
        # Fehlausloesungen durch Hintergrundgeraeusch (ab ca. 55 dB(A) spuerbar)
        rate = max(0.0, (env.noise_db - 55.0) / 10.0) * 0.03          # pro Sekunde
        dt = now - self._last_false
        self._last_false = now
        if rate > 0 and self.rng.random() < rate * dt:
            out.append(KeywordEvent(self.rng.choice(self.vocab()), self.rng.uniform(0.3, 0.72), now, "NOISE"))
        return out


# ====================================================================== Gesten
class GestureRecognizer:
    """Gestenerkennung pro Bild (Handpose + Regeln). Der Schiedsrichter haelt eine Geste ca. 2.5 s."""

    def __init__(self, cfg: Config, rng: random.Random):
        self.cfg, self.rng = cfg, rng
        self._g: tuple[str, float, float, float] | None = None    # (name, t_start, t_end, distanz)

    def perform(self, name: str, now: float, distance: float, duration: float = 2.5) -> None:
        self._g = (name, now + 0.3, now + 0.3 + duration, distance)

    def frame_p(self, distance: float, lux: float | None = None) -> float:
        lux = self.cfg.env.light_lux if lux is None else lux
        base = 0.97 - 0.10 * max(0.0, distance - 0.5)                  # 0.5 m: 0.97, 2 m: 0.82
        return max(0.05, base * light_factor(lux) ** 0.7)

    def classify_frame(self, name: str | None, distance: float, lux: float | None = None):
        """Ein Kamerabild -> (Label, Konfidenz) oder None."""
        rng = self.rng
        if name is None:
            return (rng.choice(GESTURES), rng.uniform(0.3, 0.6)) if rng.random() < 0.01 else None
        p = self.frame_p(distance, lux)
        if rng.random() < p:
            return name, min(0.99, max(0.4, 0.62 + 0.35 * p + rng.gauss(0, 0.07)))
        u = rng.random()
        if u < 0.7:
            return None
        return rng.choice([g for g in GESTURES if g != name]), rng.uniform(0.35, 0.7)

    def read(self, now: float):
        env = self.cfg.env
        if not env.camera_ok:
            return None
        name, dist = None, 1.0
        if self._g and self._g[1] <= now <= self._g[2]:
            name, dist = self._g[0], self._g[3]
        return self.classify_frame(name, dist)


# ====================================================================== Knochen
class BoneDetector:
    """Objektdetektor (Kamera): Peilung/Distanz/Konfidenz pro Bild.

    Sichtbar nur im Bildfeld (66 Grad), ausserhalb der Naechstgrenze und innerhalb der Reichweite.
    Detektionsrate sinkt mit Distanz, schlechtem Licht und knochenfarbenem Boden (KW41)."""

    RANGE = 6.0     # m, ANNAHME: Reichweite des Detektors fuer ein 21-cm-Objekt

    def __init__(self, cfg: Config, rng: random.Random, world: World):
        self.cfg, self.rng, self.world = cfg, rng, world

    def p_detect(self, dist: float) -> float:
        env = self.cfg.env
        if dist >= self.RANGE:
            return 0.0
        p = 0.96 * (1.0 - (dist / self.RANGE) ** 2) * light_factor(env.light_lux)
        return max(0.0, p * (1.0 - 0.55 * env.floor_similarity))

    def read(self, now: float) -> Detection | None:
        env, rob = self.cfg.env, self.cfg.robot
        if not env.camera_ok:
            return None
        rng = self.rng
        bearing, dist = self.world.bone_view()
        half = math.radians(rob.camera_fov_deg) / 2
        if abs(bearing) < half and rob.camera_blind <= dist:
            p = self.p_detect(dist)
            if rng.random() < p:
                conf = min(0.99, max(0.3, 0.55 + 0.45 * p + rng.gauss(0, 0.06)))
                return Detection(bearing + rng.gauss(0, math.radians(0.8)),
                                 max(0.05, dist * (1 + rng.gauss(0, 0.08))), conf, True)
        # Fehlerkennung auf knochenfarbenem Boden
        if env.floor_similarity > 0 and rng.random() < 0.04 * env.floor_similarity:
            return Detection(rng.uniform(-half, half), rng.uniform(0.8, 4.5), rng.uniform(0.35, 0.65), False)
        return None


# ====================================================================== Gesamt
class SimSensors:
    """Fasst alle Sensor-Modelle zu einem SensorFrame zusammen (Schnittstelle des Brain)."""

    def __init__(self, cfg: Config, rng: random.Random, world: World):
        self.cfg, self.rng, self.world = cfg, rng, world
        self.mic = KeywordSpotter(cfg, rng)
        self.gestures = GestureRecognizer(cfg, rng)
        self.bones = BoneDetector(cfg, rng, world)
        self._contact_since: float | None = None
        self._touch_cam_sent = False

    def read(self, now: float) -> SensorFrame:
        env = self.cfg.env
        tof = self.world.tof()
        if tof is not None:
            tof = max(0.02, tof + self.rng.gauss(0, 0.01 + 0.01 * tof))
        # kamerabasierte Beruehrungserkennung (TF22 Normalfall): Latenz ca. 0.1 s
        touch_cam = False
        if self.world.contact():
            if self._contact_since is None:
                self._contact_since = now
            if env.touch_camera_ok and env.camera_ok and not self._touch_cam_sent and now - self._contact_since >= 0.1:
                touch_cam = self.rng.random() < 0.9
                self._touch_cam_sent = touch_cam
        else:
            self._contact_since = None
            self._touch_cam_sent = False
        return SensorFrame(
            t=now,
            keywords=self.mic.read(now),
            gesture=self.gestures.read(now),
            bone=self.bones.read(now),
            tof=tof,
            touch_cam=touch_cam,
        )
