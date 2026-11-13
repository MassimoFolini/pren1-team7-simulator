"""Schnittstellen (Hardware Abstraction Layer) zwischen Brain und Aussenwelt.

Das Brain (brain.py) laeuft unveraendert im Simulator und spaeter auf dem Raspberry Pi am echten Roboter:

* Eingang Wahrnehmung:  ein `SensorSource` liefert pro Zyklus einen `SensorFrame` (perception.py)
    - Simulator:  perception.SimSensors (parametrische Modelle)
    - Roboter:    eigene Klasse mit Mikrofon (Vosk), Kamera (Handpose, Objektdetektor), Distanzsensor
* Verbindung zum Mikrocontroller: ein `McuLink` (link.py)
    - Simulator:  link.SimLink + mcu.Mcu (Firmware-Modell)
    - Roboter:    link.SerialLink (UART, gleiches Textprotokoll)
"""
from __future__ import annotations

from typing import Protocol

from .frames import SensorFrame


class SensorSource(Protocol):
    def read(self, now: float) -> SensorFrame: ...


class McuLink(Protocol):
    up: bool

    def sbc_send(self, line: str) -> None: ...

    def sbc_recv(self) -> list[str]: ...
