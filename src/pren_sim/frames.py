"""Gemeinsame Datentypen zwischen Wahrnehmung und Brain.

Diese Datei hat bewusst KEINE Abhängigkeit zum Simulator (world, plant, …): das Brain läuft unverändert
auch am echten Roboter, wo eine echte Wahrnehmung denselben `SensorFrame` liefert (siehe hal.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

WORDS = ("HIER", "BRAV", "SITZ", "SUCH")
GESTURES = ("SITZ", "PLATZ", "AUF")


@dataclass
class KeywordEvent:
    word: str          # erkanntes Wort, "[unk]" oder Fehlauslösung
    conf: float
    t: float
    truth: str = ""    # nur für die Auswertung (die Software darf das nicht lesen)


@dataclass
class Detection:
    bearing: float     # rad, links positiv (Kamerasicht)
    dist: float        # m (aus Bild geschätzt)
    conf: float
    real: bool = True  # nur Auswertung


@dataclass
class SensorFrame:
    t: float
    keywords: list = field(default_factory=list)
    gesture: tuple | None = None          # (Label, Konfidenz), pro Kamerabild
    bone: Detection | None = None
    tof: float | None = None
    touch_cam: bool = False
