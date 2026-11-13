"""Ereignisprotokoll (Quelle fuer GUI-Log und Anforderungspruefung)."""
from __future__ import annotations


class EventLog:
    def __init__(self, maxlen: int = 5000):
        self.events: list[dict] = []
        self._id = 0
        self.maxlen = maxlen

    def add(self, t: float, src: str, kind: str, text: str = "", **data) -> dict:
        self._id += 1
        ev = {"id": self._id, "t": round(t, 3), "src": src, "kind": kind, "text": text}
        if data:
            ev["data"] = data
        self.events.append(ev)
        if len(self.events) > self.maxlen:
            del self.events[: len(self.events) - self.maxlen]
        return ev

    def find(self, kind: str, **where) -> list[dict]:
        out = []
        for e in self.events:
            if e["kind"] != kind:
                continue
            d = e.get("data", {})
            if all(d.get(k) == v for k, v in where.items()):
                out.append(e)
        return out

    def since(self, last_id: int) -> list[dict]:
        return [e for e in self.events if e["id"] > last_id]
