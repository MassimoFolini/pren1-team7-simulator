"""Auswertungen über viele Läufe: Erkennungsraten (Anf. 5.1–5.3, 13.2, 13.3) und Monte-Carlo-Suchläufe (Anf. 6.x).

Entspricht den Prüfmethoden der Anforderungsliste («Testreihe je Wort», «Testreihe bei 0.5 / 1 / 2 m»).
Pass-Schwelle 90 % ist eine ANNAHME (keine Zahl vorgegeben).
"""
from __future__ import annotations

import random
import statistics
import time

from . import brain as B
from .brain import vote_gesture
from .config import Config
from .engine import Simulation
from .perception import GESTURES, GestureRecognizer, KeywordSpotter, WORDS

PASS_RATE = 0.90


def voice_matrix(n: int = 200, distances=(0.5, 1.0, 2.0), noises=(45.0, 60.0), seed: int = 1, cfg: Config | None = None) -> dict:
    cfg = cfg or Config()
    rng = random.Random(seed)
    ks = KeywordSpotter(cfg, rng)
    rows = []
    for noise in noises:
        for d in distances:
            for word in WORDS + (cfg.brain.extra_command_word,):
                ok = miss = wrong = 0
                for _ in range(n):
                    ev = ks.classify(word, d, noise, 0.0)
                    if ev is None or ev.conf < cfg.brain.cmd_conf or ev.word == "[unk]":
                        miss += 1
                    elif ev.word == word:
                        ok += 1
                    else:
                        wrong += 1
                rows.append({"word": word, "distance": d, "noise_db": noise, "n": n,
                             "correct": round(ok / n, 3), "miss": round(miss / n, 3), "wrong": round(wrong / n, 3),
                             "snr_db": round(ks.speech_snr(d, noise), 1),
                             "pass": ok / n >= PASS_RATE})
    return {"kind": "voice", "anf": "5.1 / 5.3 / 13.3", "pass_rate": PASS_RATE, "rows": rows}


def gesture_matrix(n: int = 200, distances=(0.5, 1.0, 2.0), lights=(500.0, 60.0), seed: int = 2, cfg: Config | None = None,
                   hold_s: float = 2.5) -> dict:
    """Jede Geste wird ca. 2.5 s gezeigt; der Mehrheitsfilter des Brain entscheidet (gleicher Code wie im Betrieb)."""
    cfg = cfg or Config()
    rng = random.Random(seed)
    gr = GestureRecognizer(cfg, rng)
    bc = cfg.brain
    frames_n = int(hold_s * cfg.sim.brain_hz)
    rows = []
    for lux in lights:
        for d in distances:
            for g in GESTURES:
                ok = wrong = miss = 0
                lat = []
                for _ in range(n):
                    from collections import deque
                    buf = deque(maxlen=bc.gesture_window)
                    res = None
                    for k in range(frames_n):
                        buf.append(gr.classify_frame(g, d, lux))
                        res = vote_gesture(buf, bc.gesture_conf, bc.gesture_votes)
                        if res:
                            lat.append((k + 1) / cfg.sim.brain_hz)
                            break
                    if res is None:
                        miss += 1
                    elif res[0] == g:
                        ok += 1
                    else:
                        wrong += 1
                rows.append({"gesture": g, "distance": d, "light_lux": lux, "n": n, "correct": round(ok / n, 3),
                             "miss": round(miss / n, 3), "wrong": round(wrong / n, 3),
                             "latency_s": round(statistics.mean(lat), 2) if lat else None,
                             "pass": ok / n >= PASS_RATE})
    # Fehlausloesung ohne Geste (Ruhe, 10 Minuten)
    false = 0
    from collections import deque
    buf = deque(maxlen=bc.gesture_window)
    for _ in range(int(600 * cfg.sim.brain_hz)):
        buf.append(gr.classify_frame(None, 1.0, 500.0))
        if vote_gesture(buf, bc.gesture_conf, bc.gesture_votes):
            false += 1
            buf.clear()
    return {"kind": "gesture", "anf": "5.2 / 5.3 / 13.2", "pass_rate": PASS_RATE, "rows": rows,
            "false_triggers_per_10min": false}


def monte_carlo(n: int = 30, seed: int = 100, noise=(45.0, 60.0), light=(120.0, 800.0), progress=None) -> dict:
    """n zufällige Suchläufe (Knochenlage, Licht, Lärm zufällig, SUCH per Sprache mit Wiederholung)."""
    master = random.Random(seed)
    res = []
    t0 = time.perf_counter()
    for i in range(n):
        cfg = Config()
        cfg.env.noise_db = master.uniform(*noise)
        cfg.env.light_lux = master.uniform(*light)
        cfg.env.floor_similarity = master.choice([0.0, 0.0, 0.0, 0.5])
        cfg.env.referee_distance = master.uniform(0.7, 2.0)
        sim = Simulation(cfg, seed=master.randint(0, 10 ** 6))
        sim.wait_ready()
        sim.random_bone()
        tries = 0
        while sim.brain.state == B.BEREIT and tries < 6 and not sim.log.find("search_start"):
            sim.say("SUCH")
            tries += 1
            sim.run_until(lambda s: s.log.find("search_start"), 4.0)
        if tries >= 3 and not sim.log.find("search_start"):
            sim.press_start()
            sim.run_until(lambda s: s.log.find("search_start"), 3.0)
        ok = sim.run_until(lambda s: s.log.find("run_complete"), 170.0)
        rc = sim.log.find("run_complete")
        found = sim.log.find("found")
        contact = sim.log.find("contact_true")
        lat = (found[0]["t"] - contact[0]["t"]) if (found and contact) else None
        import math
        res.append({"run": i, "completed": bool(ok), "found": bool(found), "tries_voice": tries,
                    "search_time": rc[-1]["data"]["search_time"] if rc else None,
                    "report_latency": lat, "return_cm": math.hypot(sim.plant.x, sim.plant.y) * 100 if ok else None,
                    "outside_s": sim.outside_s, "sim_time": sim.t})
        if progress:
            progress(i + 1, n)
    done = [r for r in res if r["completed"]]
    found = [r for r in res if r["found"]]
    st = [r["search_time"] for r in found if r["search_time"]]
    summary = {
        "runs": n, "found_rate": round(len(found) / n, 3), "completed_rate": round(len(done) / n, 3),
        "search_time_mean": round(statistics.mean(st), 1) if st else None,
        "search_time_max": round(max(st), 1) if st else None,
        "report_latency_max": round(max((r["report_latency"] for r in found if r["report_latency"] is not None), default=0), 2),
        "return_cm_max": round(max((r["return_cm"] for r in done), default=0), 1),
        "outside_runs": sum(1 for r in res if r["outside_s"] > 0),
        "wall_s": round(time.perf_counter() - t0, 1),
        "sim_s_total": round(sum(r["sim_time"] for r in res), 0),
    }
    return {"kind": "montecarlo", "anf": "6.2 / 6.4 / 6.6 / 3.4", "summary": summary, "runs": res}
