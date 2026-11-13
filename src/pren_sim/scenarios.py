"""Szenarien: skriptgesteuerter Schiedsrichter (JSON) für reproduzierbare Testläufe.

Ein Szenario beschreibt Umgebung, Knochenlage und eine Schrittfolge. Die Schritte laufen als Coroutine mit
Wartebedingungen (z. B. «warte bis der Roboter bereit ist», «wiederhole den Befehl bis zu 3x, falls er nicht erkannt wird»).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import brain as B
from .checks import evaluate, indicative_score, summary
from .config import Config, _merge
from .engine import Simulation

SCENARIO_DIRS = [Path(__file__).resolve().parents[2] / "scenarios", Path.cwd() / "scenarios"]


def scenario_dir(extra: str | Path | None = None) -> Path:
    for d in ([Path(extra)] if extra else []) + SCENARIO_DIRS:
        if d.is_dir():
            return d
    return SCENARIO_DIRS[0]


def list_scenarios(extra: str | Path | None = None) -> list[dict]:
    out = []
    for f in sorted(scenario_dir(extra).glob("*.json")):
        try:
            spec = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": f.stem, "title": spec.get("title", f.stem), "description": spec.get("description", "")})
        except (OSError, ValueError):
            continue
    return out


def load_scenario(name: str, extra: str | Path | None = None) -> dict:
    f = scenario_dir(extra) / f"{name}.json"
    if not f.is_file():
        raise FileNotFoundError(name)
    return json.loads(f.read_text(encoding="utf-8"))


class ScenarioRunner:
    def __init__(self, sim: Simulation, spec: dict):
        self.sim = sim
        self.spec = spec
        self.name = spec.get("title", "Szenario")
        self.steps = spec.get("steps", [])
        self.results: list[dict] = []
        self.done = False
        self.step_index = -1
        self._gen = self._run()
        self._pending = None
        self.t_start = sim.t
        self.max_s = float(spec.get("max_s", 400))
        self.aborted = False

    # ------------------------------------------------------------ Vorbereitung
    @staticmethod
    def create(spec: dict, seed: int | None = None, cfg: Config | None = None) -> "ScenarioRunner":
        cfg = (cfg or Config()).copy()
        if "config" in spec:
            _merge(cfg, spec["config"])
        for k, v in spec.get("env", {}).items():
            setattr(cfg.env, k, type(getattr(cfg.env, k))(v))
        sim = Simulation(cfg, seed=seed if seed is not None else spec.get("seed"))
        sim.link.up = cfg.env.link_ok
        sim.world.set_referee_distance(cfg.env.referee_distance)
        b = spec.get("bone", {"x": 3.0, "y": 0.0, "th": 0.4})
        if b.get("random"):
            sim.world.random_bone(sim.rng)
        else:
            sim.world.place_bone(b["x"], b["y"], b.get("th", 0.4))
        return ScenarioRunner(sim, spec)

    # ------------------------------------------------------------ Prädikate
    def _idle(self, s: Simulation) -> bool:
        b = s.brain
        return b.state in (B.BEREIT, B.PLATZ) and not b.mcu_pose_busy and s.t - b.t_last_cmd > b.bc.cooldown_s + 0.2

    def _pred(self, exp: dict, mark: int):
        def pred(s: Simulation) -> bool:
            ok = True
            if "state" in exp:
                ok &= s.brain.state == exp["state"]
            if "pose" in exp:
                ok &= s.brain.mcu_pose == exp["pose"] and not s.brain.mcu_pose_busy
            if "event" in exp:
                ok &= any(e["id"] > mark and e["kind"] == exp["event"] for e in s.log.events)
            if "cmd" in exp:
                ok &= any(e["id"] > mark and e["kind"] == "cmd" and e["data"]["name"] == exp["cmd"] for e in s.log.events)
            return ok
        return pred

    # ------------------------------------------------------------ Schritte
    def _do(self, st: dict) -> None:
        s, k = self.sim, st["do"]
        if k == "say":
            s.say(st["word"])
        elif k == "gesture":
            s.gesture(st["name"])
        elif k == "button":
            s.press_start()
        elif k == "estop":
            s.press_estop()
        elif k == "estop_release":
            s.release_estop()
        elif k == "reset":
            s.reset_after_estop()
        elif k == "env":
            s.set_env(**st["env"])
        elif k == "place_bone":
            s.place_bone(st["x"], st["y"], st.get("th"))

    def _run(self):
        s = self.sim
        for i, st in enumerate(self.steps):
            self.step_index = i
            kind = st["do"]
            label = st.get("label") or f"{kind} {st.get('word') or st.get('name') or ''}".strip()
            if kind == "wait":
                yield (lambda _s: False, float(st.get("s", 1.0)))
                continue
            if kind == "wait_event":
                res = yield (self._pred({"event": st["event"]}, 0), float(st.get("timeout", 150)))
                self.results.append({"step": label, "ok": bool(res), "attempts": 1})
                continue
            if kind in ("say", "gesture", "button") and st.get("when_ready", True):
                yield (self._idle, 60.0)
            attempts, ok = 0, False
            while attempts <= int(st.get("retries", 0)):
                attempts += 1
                mark = s.log.events[-1]["id"] if s.log.events else 0
                self._do(st)
                exp = st.get("expect")
                if not exp:
                    ok = True
                    break
                res = yield (self._pred(exp, mark), float(st.get("timeout", 8.0)))
                if res:
                    ok = True
                    break
            self.results.append({"step": label, "ok": ok, "attempts": attempts, "optional": bool(st.get("optional"))})
            yield (lambda _s: False, float(st.get("delay", 0.8)))

    # ------------------------------------------------------------ Takt
    def tick(self) -> None:
        if self.done:
            return
        s = self.sim
        if s.t - self.t_start > self.max_s:
            self.done = self.aborted = True
            return
        try:
            if self._pending is None:
                self._pending = (*next(self._gen), s.t)
            pred, timeout, t0 = self._pending
            res = None
            if pred(s):
                res = True
            elif s.t - t0 >= timeout:
                res = False
            if res is not None:
                self._pending = None
                nxt = self._gen.send(res)
                self._pending = (*nxt, s.t)
        except StopIteration:
            self.done = True

    def result(self) -> dict:
        checks = evaluate(self.sim)
        steps_ok = all(r["ok"] or r.get("optional") for r in self.results) and not self.aborted
        req = self.spec.get("required")
        if req is None:
            fails = [c for c in checks if c["status"] == "fail"]
        else:      # nur die genannten Anforderungen müssen bestanden sein
            fails = [c for c in checks if c["anf"] in req and c["status"] != "pass"]
        return {"scenario": self.name, "sim_time": round(self.sim.t, 1), "steps": self.results,
                "steps_ok": steps_ok, "aborted": self.aborted, "checks": checks, "summary": summary(checks),
                "score": indicative_score(self.sim), "passed": steps_ok and not fails,
                "expect_fail": bool(self.spec.get("expect_fail"))}


def run_scenario(spec: dict, seed: int | None = None, cfg: Config | None = None) -> dict:
    """Komplett durchlaufen lassen (ohne Echtzeit)."""
    r = ScenarioRunner.create(spec, seed, cfg)
    r.sim.wait_ready(10.0)
    while not r.done:
        for _ in range(r.sim._brain_period):
            r.sim.step()
        r.tick()
    r.sim.run_for(1.0)
    return r.result()
