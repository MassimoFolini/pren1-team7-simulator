"""Textprotokoll zwischen Einplatinenrechner (SBC, Raspberry Pi 5) und Mikrocontroller (MCU, z. B. ESP32).

Entspricht der Festlegung im MS2-Bericht: "einfache Textbefehle ueber UART, z. B. DRIVE v w, POSE SITZ".
Eine Zeile = ein Telegramm, Felder durch Leerzeichen getrennt, Abschluss mit '\\n'.
Dieselbe Syntax verwendet spaeter die echte serielle Schnittstelle (siehe link.SerialLink).
Vollstaendige Beschreibung: docs/SCHNITTSTELLEN.md
"""
from __future__ import annotations

# --- SBC -> MCU -------------------------------------------------------------
CMD_DRIVE = "DRIVE"            # DRIVE <v m/s> <w rad/s>
CMD_STOP = "STOP"              # Raeder anhalten (kein Latch)
CMD_POSE = "POSE"              # POSE STAND|SITZ|PLATZ
CMD_SHOW = "SHOW"              # SHOW HAPPY|SPIN|TAIL (Ausdruck: Schwanz/Ohren/Augen)
CMD_PING = "PING"              # Lebenszeichen
CMD_ESTOP = "ESTOP"            # Software-Not-Aus (Latch)
CMD_ESTOP_RESET = "ESTOP_RESET"
CMD_ODOM_RESET = "ODOM_RESET"  # Odometrie auf Startpose setzen

# --- MCU -> SBC -------------------------------------------------------------
MSG_ODOM = "ODOM"              # ODOM <x> <y> <th> <v> <w>
MSG_POSE = "POSE"              # POSE <STAND|SITZ|PLATZ|MOVING> <DONE|BUSY>
MSG_BAT = "BAT"                # BAT <soc 0..1> <wh_used>
MSG_EVT = "EVT"                # EVT TOUCH | ESTOP <hw|sw> | ESTOP_CLEARED | BTN_START | WDG
MSG_ERR = "ERR"                # ERR <code> [text]
MSG_PONG = "PONG"

POSES = ("STAND", "SITZ", "PLATZ")
SHOWS = ("HAPPY", "SPIN", "TAIL")


def fmt_drive(v: float, w: float) -> str:
    return f"{CMD_DRIVE} {v:.3f} {w:.3f}"


def fmt_odom(x: float, y: float, th: float, v: float, w: float) -> str:
    return f"{MSG_ODOM} {x:.4f} {y:.4f} {th:.5f} {v:.3f} {w:.3f}"


def parse(line: str) -> tuple[str, list[str]]:
    parts = line.strip().split()
    if not parts:
        return "", []
    return parts[0].upper(), parts[1:]
