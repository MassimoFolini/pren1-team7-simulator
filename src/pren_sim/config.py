"""Konfiguration des Simulators.

Alle Zahlen mit Quelle: Aufgabenstellung HS26 (AS), FAQ, Besprechung KW41 (KW41),
Anforderungsliste V4 (Anf.), MS2-Kurzbericht (MS2). Werte mit "ANNAHME" sind Schaetzungen
des Teams/Assistenten und im Team zu bestaetigen (siehe docs/ANNAHMEN.md).
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, fields, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path


@dataclass
class FieldConfig:
    # Startfeld 20 x 50 cm (AS Folie 5; Breite x Laenge). Ursprung = Mitte Startfeld.
    start_field_w: float = 0.20
    start_field_l: float = 0.50
    # Suchbereich: 30-Grad-Segment, ca. 5 m Aktionsweite (AS, Anf. 6.1).
    # ANNAHME: Scheitel im Startfeld-Mittelpunkt, Achse in +x (Abb. 3 der AS liegt dem Simulator nicht vor).
    sector_angle_deg: float = 30.0
    sector_radius: float = 5.0
    sector_axis_deg: float = 0.0
    # Interaktionsbereich: Radius 1.5 m (KW41, Anf. 5.4); Schiedsrichter 0.5-2 m vor dem Gesicht (FAQ 14).
    interaction_radius: float = 1.5
    interaction_min: float = 0.5
    interaction_max: float = 2.0
    # Knochen ca. 21 cm (Anf. 6.2); Breite ANNAHME.
    bone_length: float = 0.21
    bone_width: float = 0.05
    # Toleranz fuer "im Spielfeld bleiben" (FAQ 6).
    field_margin: float = 0.15


@dataclass
class RobotConfig:
    # Abmasse (Anf. 1.1: max. 20 x 50 x 50; Skizze Differentialantrieb: Laenge ca. 41 cm, Spurbreite ca. 17 cm, Rad 8 cm)
    length: float = 0.41
    width: float = 0.17
    track: float = 0.17
    wheel_radius: float = 0.04
    nose_offset: float = 0.22       # Mitte -> Nase (vorn)
    front_edge: float = 0.20        # Mitte -> Vorderkante des Koerpers
    # Antrieb (ANNAHME)
    v_free: float = 0.75            # m/s Leerlaufgeschwindigkeit bei Duty 1.0
    v_max: float = 0.60             # m/s Begrenzung
    w_max: float = 2.5              # rad/s Begrenzung
    accel: float = 1.2              # m/s^2
    alpha: float = 6.0              # rad/s^2
    motor_tau: float = 0.12         # s, Zeitkonstante Motor + Last
    brake_tau: float = 0.04         # s, Notbremse (Aus + Kurzschlussbremse)
    encoder_cpr: int = 1440         # Ticks pro Radumdrehung (ANNAHME)
    wheel_radius_err: float = 0.015  # +-1.5 % Radius-Toleranz (Odometrie-Drift)
    track_err: float = 0.02
    gyro_bias_dps: float = 0.05     # +- Gyro-Bias in Grad/s
    gyro_noise_dps: float = 0.3
    # Haltungswechsel in Sekunden (ANNAHME, in MS3 mit Hebel/Drehmoment auslegen)
    t_sit: float = 1.2
    t_down: float = 1.8
    t_stand: float = 1.5
    # Sensoren
    camera_fov_deg: float = 66.0    # Kamera Standard ca. 66 Grad (Entscheid Team, MS2)
    camera_offset: float = 0.18
    camera_blind: float = 0.30      # m, Knochen unter dieser Distanz nicht mehr im Bild
    tof_range: float = 4.0
    tof_beam_deg: float = 2.5
    # Energie (Stromversorgung-Recherche: ca. 21 W Mittel, 38.4 Wh) - ANNAHME
    battery_wh: float = 38.4
    p_base_w: float = 10.0          # Rechner + Mikrocontroller + Sensorik + Display
    p_motor_max_w: float = 14.0
    p_servo_hold_w: float = 3.0
    p_servo_move_w: float = 9.0


@dataclass
class EnvConfig:
    noise_db: float = 45.0          # Umgebungslaerm (Anf. 13.3: bis ca. 60 dB(A))
    light_lux: float = 500.0        # Raumlicht (Anf. 13.2: ca. 200-1000 lx)
    floor_similarity: float = 0.0   # 0..1: Boden knochenfarben (KW41)
    referee_distance: float = 1.5   # m vor dem Gesicht des Hundes
    speech_level_db_1m: float = 62.0  # ANNAHME: Sprechpegel in 1 m
    camera_ok: bool = True
    mic_ok: bool = True
    link_ok: bool = True
    touch_taster_ok: bool = True
    touch_camera_ok: bool = True


@dataclass
class BrainConfig:
    cmd_conf: float = 0.60          # Mindest-Konfidenz Sprachbefehl
    gesture_conf: float = 0.60
    gesture_window: int = 8         # letzte Frames
    gesture_votes: int = 5          # davon mindestens
    cooldown_s: float = 1.5         # Sperre nach akzeptiertem Befehl
    bone_conf: float = 0.55
    bone_confirm: int = 3           # Treffer
    bone_confirm_window: float = 1.2
    search_timeout_s: float = 120.0  # Abbruch nach 2 Minuten (AS Folie 7)
    trick_max_s: float = 60.0       # Kunststueck max. 1 Min (Anf. 5.13)
    search_speed: float = 0.30
    approach_speed: float = 0.30
    cruise_speed: float = 0.45
    here_stop_distance: float = 0.55
    here_max_travel: float = 1.8
    found_hold_s: float = 1.0
    startup_s: float = 2.0          # Selbsttest (Start max. 1 Minute, AS Folie 4)
    link_timeout_s: float = 0.6
    return_tol: float = 0.04
    heading_tol_deg: float = 3.0
    extra_command_word: str = "KUNSTSTUECK"   # PLATZHALTER: Zusatzbefehl ist noch nicht definiert
    use_taster_fallback: bool = True


@dataclass
class SimConfig:
    dt: float = 0.01                # Physik/Firmware-Schritt (100 Hz)
    brain_hz: float = 20.0          # Wahrnehmung + Zustandsautomat (Pi)
    link_latency_s: float = 0.006   # UART-Latenz
    seed: int = 7


@dataclass
class Config:
    field: FieldConfig = dc_field(default_factory=FieldConfig)
    robot: RobotConfig = dc_field(default_factory=RobotConfig)
    env: EnvConfig = dc_field(default_factory=EnvConfig)
    brain: BrainConfig = dc_field(default_factory=BrainConfig)
    sim: SimConfig = dc_field(default_factory=SimConfig)

    def copy(self) -> "Config":
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "Config":
        cfg = Config()
        if d:
            _merge(cfg, d)
        return cfg

    @staticmethod
    def load(path: str | Path) -> "Config":
        return Config.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def sector_half(self) -> float:
        return math.radians(self.field.sector_angle_deg) / 2.0

    @property
    def sector_axis(self) -> float:
        return math.radians(self.field.sector_axis_deg)


def _merge(obj, d: dict) -> None:
    names = {f.name for f in fields(obj)}
    for k, v in d.items():
        if k not in names:
            raise KeyError(f"Unbekannter Konfigurationsschluessel: {k}")
        cur = getattr(obj, k)
        if is_dataclass(cur) and isinstance(v, dict):
            _merge(cur, v)
        else:
            setattr(obj, k, type(cur)(v) if cur is not None and not isinstance(v, type(cur)) else v)
