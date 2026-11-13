"""Kommandozeile: python -m pren_sim <befehl>"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _print_checks(res: dict) -> None:
    sym = {"pass": "OK  ", "fail": "FAIL", "warn": "WARN", "open": "offen", "n.a.": "n.a."}
    for c in res["checks"]:
        if c["status"] == "open":
            continue
        print(f"   [{sym[c['status']]}] Anf. {c['anf']:<9} {c['text']}  {c['value']}  {('(' + c['limit'] + ')') if c['limit'] else ''}")


def cmd_run(a) -> int:
    from .scenarios import list_scenarios, load_scenario, run_scenario
    ids = [s["id"] for s in list_scenarios(a.dir)] if (a.all or not a.scenario) else [a.scenario]
    bad = 0
    for sid in ids:
        path = Path(sid)
        spec = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" and path.exists() else load_scenario(sid, a.dir)
        res = run_scenario(spec, seed=a.seed)
        ok = res["passed"]
        bad += 0 if ok else 1
        print(f"{'BESTANDEN' if ok else 'FEHLGESCHLAGEN':<15} {spec.get('title', sid)}  (Simulationszeit {res['sim_time']} s)")
        for r in res["steps"]:
            if not r["ok"] and not r.get("optional"):
                print(f"   Schritt nicht erreicht: {r['step']} (Versuche: {r['attempts']})")
            elif r["attempts"] > 1:
                print(f"   Schritt «{r['step']}» brauchte {r['attempts']} Versuche")
        if a.verbose or not ok:
            _print_checks(res)
    print(f"\n{len(ids) - bad}/{len(ids)} Szenarien bestanden")
    return 1 if bad else 0


def _table(rows: list[dict], cols: list[str]) -> None:
    w = [max(len(c), *(len(str(r.get(c, ''))) for r in rows)) for c in cols]
    print("  ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
    for r in rows:
        print("  ".join(str(r.get(c, '')).ljust(w[i]) for i, c in enumerate(cols)))


def cmd_test_recognition(a) -> int:
    from .experiments import gesture_matrix, voice_matrix
    v = voice_matrix(n=a.n)
    print(f"Sprachbefehle (Anf. {v['anf']}), n={a.n} je Zelle, Schwelle {int(v['pass_rate'] * 100)} %\n")
    _table(v["rows"], ["word", "distance", "noise_db", "snr_db", "correct", "miss", "wrong", "pass"])
    g = gesture_matrix(n=max(20, a.n // 2))
    print(f"\nGesten (Anf. {g['anf']}), Fehlauslösungen in 10 min Ruhe: {g['false_triggers_per_10min']}\n")
    _table(g["rows"], ["gesture", "distance", "light_lux", "correct", "miss", "wrong", "latency_s", "pass"])
    return 0


def cmd_montecarlo(a) -> int:
    from .experiments import monte_carlo
    m = monte_carlo(n=a.n, seed=a.seed)
    print(json.dumps(m["summary"], indent=2, ensure_ascii=False))
    return 0


def cmd_bench(a) -> int:
    from .bench import run
    print(json.dumps(run(a.seconds), indent=2, ensure_ascii=False))
    return 0


def cmd_serve(a) -> int:
    from .server import serve
    serve(a.host, a.port, a.seed, a.speed, a.dir, a.config, a.open)
    return 0


def cmd_list(a) -> int:
    from .scenarios import list_scenarios
    for s in list_scenarios(a.dir):
        print(f"{s['id']:<34} {s['title']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8()
    ap = argparse.ArgumentParser(prog="pren_sim", description=f"PREN1 Team 7 – Simulator Hunde-Roboter v{__version__}")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="Weboberfläche starten (Standard)")
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 für Zugriff aus dem Netz (z. B. Pi -> Laptop)")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--seed", type=int, default=None)
    s.add_argument("--speed", type=float, default=1.0)
    s.add_argument("--dir", default=None, help="Ordner mit Szenario-JSON")
    s.add_argument("--config", default=None, help="JSON mit Konfigurationswerten")
    s.add_argument("--open", action="store_true", help="Browser öffnen")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("run", help="Szenario(en) ohne Oberfläche durchlaufen lassen")
    s.add_argument("scenario", nargs="?")
    s.add_argument("--all", action="store_true")
    s.add_argument("--seed", type=int, default=None)
    s.add_argument("--dir", default=None)
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("list", help="Szenarien auflisten")
    s.add_argument("--dir", default=None)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("test-recognition", help="Erkennungsraten (Sprache/Gesten) nach Distanz, Lärm, Licht")
    s.add_argument("-n", type=int, default=200)
    s.set_defaults(fn=cmd_test_recognition)

    s = sub.add_parser("montecarlo", help="Viele zufällige Suchläufe")
    s.add_argument("-n", type=int, default=50)
    s.add_argument("--seed", type=int, default=100)
    s.set_defaults(fn=cmd_montecarlo)

    s = sub.add_parser("bench", help="Leistungsmessung (Raspberry Pi 5 / Laptop)")
    s.add_argument("--seconds", type=float, default=120.0)
    s.set_defaults(fn=cmd_bench)

    a = ap.parse_args(argv)
    if not a.cmd:
        a = ap.parse_args(["serve"] + (argv or []))
    return a.fn(a)
