"""Automatische Pruefung der Anforderungen (Anforderungsliste V4) anhand des Ereignisprotokolls.

Jede Pruefung traegt die Nummer der Anforderung. Status: pass | fail | warn | open (noch nicht getestet) | n.a.
Grenzwerte mit "ANNAHME" sind in der Anforderungsliste nicht beziffert (siehe docs/ANNAHMEN.md).
"""
from __future__ import annotations

import math

from .geometry import wrap

LIM_ACK_S = 0.5            # ANNAHME: Quittierung "eindeutig, sofort"
LIM_REPORT_S = 1.0         # ANNAHME: Fundmeldung am Ort der Beruehrung
LIM_POSE_S = 4.0           # ANNAHME: Haltungswechsel
LIM_ESTOP_S = 0.3          # ANNAHME: "sofortiger Stopp"
LIM_SEARCH_S = 120.0       # Anf. 6.6 / AS Folie 7
LIM_TRICK_S = 60.0         # Anf. 5.13
LIM_RUNTIME_MIN = 12.0     # Anf. 4.3 (Entscheid Team 30.10.2026)
LIM_START_S = 60.0         # AS Folie 4: Roboter aufstarten max. 1 Minute
LIM_HERE_M = 0.3           # ANNAHME: "erkennbare Bewegung auf die Person zu"
LIM_RETURN_M = 0.10        # ANNAHME: Rueckkehr ins Startfeld (Mitte)


def _c(anf: str, text: str, status: str, value: str = "", limit: str = "") -> dict:
    return {"anf": anf, "text": text, "status": status, "value": value, "limit": limit}


def evaluate(sim) -> list[dict]:
    log, cfg = sim.log, sim.cfg
    ev = log.events
    out: list[dict] = []

    # 8.2 / 4.2 Grundlagen
    out.append(_c("4.2", "Keine externe Datenverbindung (Betrieb offline)", "pass", "Simulator ohne Netzwerkzugriff"))
    ready = log.find("startup_ready")
    if ready:
        t = ready[0]["data"]["t_ready"]
        out.append(_c("AS", "Roboter startklar (max. 1 Minute)", "pass" if t <= LIM_START_S else "fail", f"{t:.1f} s", f"≤ {LIM_START_S:.0f} s"))
    else:
        out.append(_c("AS", "Roboter startklar (max. 1 Minute)", "open"))

    # 5.5 Quittierung
    cmds = log.find("cmd")
    if cmds:
        late = []
        for c in cmds:
            acks = [a for a in log.find("ack", cmd=c["data"]["name"]) if 0 <= a["t"] - c["t"] <= LIM_ACK_S]
            if not acks:
                late.append(c["data"]["name"])
        out.append(_c("5.5", "Jeder erkannte Befehl wird quittiert", "fail" if late else "pass",
                      f"{len(cmds) - len(late)}/{len(cmds)} quittiert", f"≤ {LIM_ACK_S} s"))
    else:
        out.append(_c("5.5", "Jeder erkannte Befehl wird quittiert", "open"))

    # 5.6 HIER
    h = log.find("here_done")
    if h:
        m = h[-1]["data"]["travelled"]
        out.append(_c("5.6", "HIER: Bewegung auf die Person zu", "pass" if m >= LIM_HERE_M else "warn", f"{m:.2f} m", f"≥ {LIM_HERE_M} m"))
    else:
        out.append(_c("5.6", "HIER: Bewegung auf die Person zu", "open"))

    # 5.8 BRAV
    br = log.find("cmd", name="BRAV")
    out.append(_c("5.8", "BRAV: erkennbare Reaktion (Emotion)", "pass" if br else "open",
                  f"{len(br)}x erkannt" if br else ""))

    # 5.9 - 5.12 Haltungen
    def pose_check(anf, text, name, src, pose):
        hits = [e for e in log.find("cmd", name=name, source=src)]
        if not hits:
            return _c(anf, text, "open")
        ok = 0
        for c in hits:
            if any(0 <= p["t"] - c["t"] <= LIM_POSE_S and p["data"]["pose"] == pose for p in log.find("pose_done")):
                ok += 1
        return _c(anf, text, "pass" if ok == len(hits) else "fail", f"{ok}/{len(hits)}", f"≤ {LIM_POSE_S:.0f} s")

    out.append(pose_check("5.9", "Sprache SITZ: Sitzposition", "SITZ", "voice", "SITZ"))
    out.append(pose_check("5.10", "Geste SITZ: Sitzposition", "SITZ", "gesture", "SITZ"))
    out.append(pose_check("5.11", "Geste PLATZ: Liegeposition", "PLATZ", "gesture", "PLATZ"))
    out.append(pose_check("5.12", "Geste AUF: Stand auf vier Beinen", "AUF", "gesture", "STAND"))

    # 5.13 Kunststueck
    td = log.find("trick_done")
    if td:
        d = td[-1]["data"]["duration"]
        out.append(_c("5.13", "Zusatzbefehl (Kunststueck, PLATZHALTER) höchstens 1 Min", "pass" if d <= LIM_TRICK_S else "fail", f"{d:.1f} s", f"≤ {LIM_TRICK_S:.0f} s"))
    else:
        out.append(_c("5.13", "Zusatzbefehl (Kunststueck, PLATZHALTER) höchstens 1 Min", "open"))

    # Suche
    starts = log.find("search_start")
    turn = log.find("turn_done")
    out.append(_c("3.3/5.7", "SUCH: Umdrehen zum Suchbereich", "pass" if turn else ("open" if not starts else "fail"),
                  f"{len(turn)}x" if turn else ""))
    touch_true = log.find("contact_true")
    found = log.find("found")
    runs = log.find("run_complete")
    if starts:
        out.append(_c("6.2/6.3", "Knochen gefunden und beruehrt", "pass" if touch_true else "fail",
                      "Kontakt bei t=%.1f s" % touch_true[0]["t"] if touch_true else "kein Kontakt"))
        if touch_true and found:
            lat = found[0]["t"] - touch_true[0]["t"]
            out.append(_c("6.4", "Fund am Ort der Beruehrung gemeldet", "pass" if 0 <= lat <= LIM_REPORT_S else "fail", f"{lat:.2f} s nach Kontakt", f"≤ {LIM_REPORT_S} s"))
        else:
            out.append(_c("6.4", "Fund am Ort der Beruehrung gemeldet", "fail" if starts and (runs or log.find("abort")) else "open"))
    else:
        out.append(_c("6.2/6.3", "Knochen gefunden und beruehrt", "open"))
        out.append(_c("6.4", "Fund am Ort der Beruehrung gemeldet", "open"))
    if runs:
        r = runs[-1]["data"]
        ok_time = r["search_time"] <= LIM_SEARCH_S and r["reason"] != "timeout"
        out.append(_c("6.6", "Suchvorgang innerhalb 2 Minuten abgeschlossen", "pass" if ok_time else "fail",
                      f"{r['search_time']:.1f} s ({'gefunden' if r['reason'] == 'found' else 'Abbruch'})", f"≤ {LIM_SEARCH_S:.0f} s"))
        tr = log.find("run_truth")
        td = tr[-1]["data"] if tr else {"x": sim.plant.x, "y": sim.plant.y, "th": sim.plant.th, "pose": sim.plant.pose,
                                         "in_start_field": sim.world.in_start_field()}
        dev = math.hypot(td["x"], td["y"])
        dth = abs(math.degrees(wrap(td["th"] - math.pi)))
        out.append(_c("3.4/3.5", "Rueckkehr ins Startfeld, sitzend",
                      "pass" if (td["in_start_field"] and td["pose"] == "SITZ" and dev <= LIM_RETURN_M) else "fail",
                      f"Abweichung {dev * 100:.0f} cm, {dth:.0f}° Richtung, {td['pose']}", f"≤ {LIM_RETURN_M * 100:.0f} cm im Startfeld"))
    else:
        out.append(_c("6.6", "Suchvorgang innerhalb 2 Minuten abgeschlossen", "open"))
        out.append(_c("3.4/3.5", "Rueckkehr ins Startfeld, sitzend", "open"))
    tast = [c for c in log.find("cmd", name="SUCH") if c["data"]["source"] == "taster"]
    out.append(_c("6.5", "Suchstart per Taster (Fallback)", "pass" if tast else "open", f"{len(tast)}x" if tast else ""))

    # Spielfeld
    if starts:
        if sim.outside_s > 0.0:
            out.append(_c("7.3/FAQ6", "Im Spielfeld bleiben", "warn", f"{sim.outside_s:.1f} s ausserhalb (max. {sim.max_outside * 100:.0f} cm)", "0 s"))
        else:
            out.append(_c("7.3/FAQ6", "Im Spielfeld bleiben", "pass", "nie ausserhalb"))

    # Not-Aus
    st = log.find("stopped")
    if st:
        d = st[-1]["data"]["stop_time"]
        out.append(_c("7.1", "Not-Aus: Roboter steht sofort", "pass" if d <= LIM_ESTOP_S else "fail", f"{d:.2f} s", f"≤ {LIM_ESTOP_S} s"))
    else:
        out.append(_c("7.1", "Not-Aus: Roboter steht sofort", "open"))

    # Energie / Laufzeit
    if sim.t > 20:
        avg_w = sim.plant.energy_wh / sim.t * 3600.0
        minutes = cfg.robot.battery_wh / max(avg_w, 1e-6) * 60.0
        out.append(_c("4.3", "Akku-Laufzeit (aus mittlerer Leistung hochgerechnet)", "pass" if minutes >= LIM_RUNTIME_MIN else "fail",
                      f"{minutes:.0f} min bei Ø {avg_w:.1f} W", f"≥ {LIM_RUNTIME_MIN:.0f} min"))
    else:
        out.append(_c("4.3", "Akku-Laufzeit (aus mittlerer Leistung hochgerechnet)", "open"))
    return out


def summary(checks: list[dict]) -> dict:
    s = {"pass": 0, "fail": 0, "warn": 0, "open": 0}
    for c in checks:
        s[c["status"]] = s.get(c["status"], 0) + 1
    return s


def indicative_score(sim, scenario_ok_commands: int | None = None) -> dict:
    """Orientierungswert nach Bewertungsschema Folie 13 (PREN2). Die Teilpunkte und die Zeitformel sind NICHT vorgegeben
    -> Annahme: Grundbefehle je 10 Punkte, Suche 40 Punkte linear nach Zeit, Zusatzbefehl hier nicht bewertbar (Publikum)."""
    log = sim.log
    ok = len({(c["data"]["name"], c["data"]["source"]) for c in log.find("cmd") if c["data"]["name"] in ("SITZ", "PLATZ", "AUF", "HIER", "BRAV")})
    basic = min(4, ok) * 10
    runs = log.find("run_complete")
    search = 0.0
    if runs and runs[-1]["data"]["reason"] == "found":
        t = runs[-1]["data"]["search_time"]
        search = round(40.0 * max(0.0, 1.0 - 0.5 * t / 120.0), 1)
    return {"grundbefehle": basic, "suche": search, "zusatz": "Publikum", "total_ohne_zusatz": basic + search,
            "hinweis": "Orientierung; Teilpunkte/Zeitformel sind nicht vorgegeben (Annahme)"}
