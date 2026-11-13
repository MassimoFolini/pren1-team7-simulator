"""Verbindung SBC <-> MCU: simuliert (SimLink) oder echt seriell (SerialLink, optional)."""
from __future__ import annotations

from collections import deque


class SimLink:
    """Zwei Warteschlangen mit Latenz; bei link_up=False gehen Telegramme verloren (Fehlerinjektion)."""

    def __init__(self, latency_s: float = 0.006):
        self.latency = latency_s
        self.up = True
        self._to_mcu: deque[tuple[float, str]] = deque()
        self._to_sbc: deque[tuple[float, str]] = deque()
        self.now = 0.0
        self.tx_count = 0
        self.rx_count = 0

    # Zeit wird von der Engine gesetzt
    def tick(self, now: float) -> None:
        self.now = now

    # --- Seite SBC
    def sbc_send(self, line: str) -> None:
        self.tx_count += 1
        if self.up:
            self._to_mcu.append((self.now + self.latency, line))

    def sbc_recv(self) -> list[str]:
        return self._drain(self._to_sbc)

    # --- Seite MCU
    def mcu_send(self, line: str) -> None:
        if self.up:
            self._to_sbc.append((self.now + self.latency, line))

    def mcu_recv(self) -> list[str]:
        return self._drain(self._to_mcu)

    def _drain(self, q: deque) -> list[str]:
        out = []
        while q and q[0][0] <= self.now:
            out.append(q.popleft()[1])
        self.rx_count += len(out)
        return out


class SerialLink:
    """Echte UART-Anbindung des Raspberry Pi an den Mikrocontroller (nur SBC-Seite).

    Benoetigt `pyserial` (pip install pyserial). Bisher NICHT gegen echte Hardware getestet.
    """

    def __init__(self, port: str = "/dev/serial0", baud: int = 115200):
        import serial  # lazy import: im Simulator nicht noetig

        self._ser = serial.Serial(port, baud, timeout=0)
        self._buf = b""
        self.up = True

    def sbc_send(self, line: str) -> None:
        self._ser.write((line.strip() + "\n").encode("ascii"))

    def sbc_recv(self) -> list[str]:
        self._buf += self._ser.read(4096)
        *lines, self._buf = self._buf.split(b"\n")
        return [l.decode("ascii", "ignore").strip() for l in lines if l.strip()]
