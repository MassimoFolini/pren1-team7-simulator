"""Web-Server des Simulators (nur Standardbibliothek, läuft auf Laptop und Raspberry Pi 5, komplett offline).

* Statische Dateien der Weboberfläche (web/)
* Server-Sent-Events (/api/stream) mit dem Zustand des Digital Twins (20 Hz)
* JSON-API zum Bedienen (Schiedsrichter, Umgebung, Szenarien, Tests)

Standardmässig nur auf 127.0.0.1 erreichbar. Für den Zugriff vom Laptop auf den Pi: --host 0.0.0.0
(nur im lokalen Netz; Anforderung 4.2 gilt für den Betrieb des Roboters, nicht für die Anzeige des Simulators).
"""
from __future__ import annotations

import json
import mimetypes
import platform
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from . import brain as B
from .checks import evaluate, indicative_score, summary
from .config import Config
from .engine import Simulation
from .experiments import gesture_matrix, monte_carlo, voice_matrix
from .scenarios import ScenarioRunner, list_scenarios, load_scenario

WEB_DIR = Path(__file__).resolve().parent / "web"


class SimHost:
    """Hält die laufende Simulation (Echtzeit-Thread) und serialisiert alle Zugriffe."""

    def __init__(self, cfg: Config | None = None, seed: int | None = None, scenario_dir: str | None = None):
        self.base_cfg = cfg or Config()
        self.scenario_dir = scenario_dir
        self.lock = threading.RLock()
        self.speed = 1.0
        self.sim = Simulation(self.base_cfg, seed=seed)
        self.runner: ScenarioRunner | None = None
        self.scenario_result: dict | None = None
        self._checks: list[dict] = []
        self._checks_t = -1.0
        self._stop = False
        self.jobs: dict[str, dict] = {}
        self.reset_epoch = 0
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sim-loop")
        self.load_avg = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------ Echtzeit-Schleife
    def _loop(self) -> None:
        last = time.perf_counter()
        acc = 0.0
        while not self._stop:
            now = time.perf_counter()
            wall = now - last
            last = now
            t_work0 = now
            with self.lock:
                sim = self.sim
                if not sim.paused:
                    acc += wall * self.speed
                    dt = sim.cfg.sim.dt
                    n = int(acc / dt)
                    if n > 3000:            # Rechner zu langsam: nicht aufholen
                        n, acc = 3000, 0.0
                    else:
                        acc -= n * dt
                    period = sim._brain_period
                    for _ in range(n):
                        sim.step()
                        if self.runner and not self.runner.done and sim.n % period == 0:
                            self.runner.tick()
                            if self.runner.done:
                                self.scenario_result = self.runner.result()
            busy = time.perf_counter() - t_work0
            self.load_avg = 0.95 * self.load_avg + 0.05 * min(1.0, busy / max(wall, 1e-3))
            time.sleep(0.008)

    # ------------------------------------------------------------------ Zustand
    def checks(self) -> list[dict]:
        if self.sim.t - self._checks_t > 0.5 or self.sim.t < self._checks_t:
            self._checks = evaluate(self.sim)
            self._checks_t = self.sim.t
        return self._checks

    def snapshot(self, last_id: int, full: bool) -> dict:
        with self.lock:
            snap = self.sim.snapshot(last_id)
            if not full:
                snap.pop("trail_true", None)
                snap.pop("trail_odom", None)
            snap["speed"] = self.speed
            snap["epoch"] = self.reset_epoch
            snap["checks"] = self.checks()
            snap["checks_summary"] = summary(snap["checks"])
            snap["score"] = indicative_score(self.sim)
            snap["load"] = round(self.load_avg, 2)
            r = self.runner
            snap["scenario"] = None if r is None else {
                "name": r.name, "running": not r.done, "step": r.step_index + 1, "steps": len(r.steps),
                "results": r.results, "result": self.scenario_result}
            return snap

    # ------------------------------------------------------------------ Bedienung
    def reset(self, seed: int | None = None, spec: dict | None = None) -> None:
        with self.lock:
            self.reset_epoch += 1
            self.scenario_result = None
            self.runner = None
            if spec is not None:
                self.runner = ScenarioRunner.create(spec, seed)
                self.sim = self.runner.sim
            else:
                self.sim = Simulation(self.base_cfg, seed=seed)
            self.sim.paused = False
            self._checks_t = -1.0

    def run_scenario(self, sid: str, seed: int | None = None) -> None:
        spec = load_scenario(sid, self.scenario_dir)
        self.reset(seed, spec)

    def command(self, path: str, body: dict) -> dict:
        with self.lock:
            s = self.sim
            if path == "say":
                s.say(str(body["word"]))
            elif path == "gesture":
                s.gesture(str(body["name"]))
            elif path == "button":
                s.press_start()
            elif path == "estop":
                s.press_estop()
            elif path == "estop_release":
                s.release_estop()
            elif path == "estop_reset":
                s.reset_after_estop()
            elif path == "env":
                s.set_env(**body)
            elif path == "bone":
                if body.get("random"):
                    s.random_bone()
                else:
                    s.place_bone(float(body["x"]), float(body["y"]), None if body.get("th") is None else float(body["th"]))
            elif path == "sim":
                if "speed" in body:
                    self.speed = max(0.1, min(float(body["speed"]), 50.0))
                if "paused" in body:
                    s.paused = bool(body["paused"])
                if body.get("reset"):
                    self.reset(body.get("seed"))
            elif path == "scenario":
                self.run_scenario(str(body["id"]), body.get("seed"))
            elif path == "scenario_stop":
                self.runner = None
            else:
                raise KeyError(path)
        return {"ok": True}

    # ------------------------------------------------------------------ Auswertungen (Hintergrund)
    def start_job(self, kind: str, n: int) -> dict:
        with self.lock:
            j = self.jobs.get(kind)
            if j and j["state"] == "running":
                return j
            job = {"kind": kind, "state": "running", "progress": 0.0, "result": None, "started": time.time(), "n": n}
            self.jobs[kind] = job

        def work():
            try:
                cfg = self.base_cfg
                if kind == "voice":
                    job["result"] = voice_matrix(n=n, cfg=cfg)
                elif kind == "gesture":
                    job["result"] = gesture_matrix(n=n, cfg=cfg)
                elif kind == "montecarlo":
                    job["result"] = monte_carlo(n=n, progress=lambda i, m: job.__setitem__("progress", i / m))
                job["state"] = "done"
            except Exception as e:      # noqa: BLE001 - Fehler dem Bediener zeigen
                job["state"] = "error"
                job["error"] = repr(e)
            job["progress"] = 1.0
        threading.Thread(target=work, daemon=True, name=f"job-{kind}").start()
        return job


def make_handler(host: SimHost):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"PRENSim/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):      # ruhig
            pass

        # ---- Helfer
        def _json(self, obj, code: int = 200) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(min(n, 1_000_000)).decode("utf-8") or "{}")

        # ---- GET
        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            p = u.path
            try:
                if p == "/api/stream":
                    return self._stream()
                if p == "/api/state":
                    return self._json(host.snapshot(0, True))
                if p == "/api/scenarios":
                    return self._json(list_scenarios(host.scenario_dir))
                if p == "/api/config":
                    return self._json(host.sim.cfg.to_dict())
                if p == "/api/fsm":
                    return self._json({"states": B.STATES, "transitions": B.TRANSITIONS})
                if p == "/api/info":
                    return self._json({"version": __version__, "python": platform.python_version(),
                                       "platform": platform.platform(), "machine": platform.machine()})
                if p == "/api/jobs":
                    return self._json(host.jobs)
                return self._static(p)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:     # noqa: BLE001
                self._json({"error": repr(e)}, 500)

        def _static(self, p: str) -> None:
            rel = "index.html" if p in ("/", "") else p.lstrip("/")
            f = (WEB_DIR / rel).resolve()
            if WEB_DIR not in f.parents and f != WEB_DIR or not f.is_file():
                return self._json({"error": "nicht gefunden"}, 404)
            data = f.read_bytes()
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def _stream(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last_id, epoch, full = 0, -1, True
            try:
                while True:
                    snap = host.snapshot(last_id, full)
                    if snap["epoch"] != epoch:          # erster Aufruf oder Reset: vollständiger Zustand
                        snap = host.snapshot(0, True)
                        epoch = snap["epoch"]
                    if snap["events"]:
                        last_id = snap["events"][-1]["id"]
                    full = False
                    self.wfile.write(b"data: " + json.dumps(snap, ensure_ascii=False).encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

        # ---- POST
        def do_POST(self):  # noqa: N802
            p = urlparse(self.path).path
            try:
                body = self._body()
                if p.startswith("/api/test/"):
                    kind = p.rsplit("/", 1)[-1]
                    if kind not in ("voice", "gesture", "montecarlo"):
                        return self._json({"error": "unbekannt"}, 404)
                    default = {"voice": 200, "gesture": 100, "montecarlo": 30}[kind]
                    n = max(5, min(int(body.get("n", default)), 2000 if kind != "montecarlo" else 300))
                    return self._json(host.start_job(kind, n))
                if p.startswith("/api/"):
                    return self._json(host.command(p[5:], body))
                self._json({"error": "nicht gefunden"}, 404)
            except KeyError as e:
                self._json({"error": f"unbekannt/fehlend: {e}"}, 400)
            except (ValueError, FileNotFoundError, TypeError) as e:
                self._json({"error": repr(e)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def serve(host_addr: str = "127.0.0.1", port: int = 8080, seed: int | None = None, speed: float = 1.0,
          scenario_dir: str | None = None, config_path: str | None = None, open_browser: bool = False) -> None:
    cfg = Config.load(config_path) if config_path else Config()
    host = SimHost(cfg, seed, scenario_dir)
    host.speed = speed
    host.start()
    httpd = ThreadingHTTPServer((host_addr, port), make_handler(host))
    httpd.daemon_threads = True
    url = f"http://{'localhost' if host_addr in ('0.0.0.0', '127.0.0.1') else host_addr}:{port}/"
    print(f"PREN-Simulator {__version__} läuft: {url}   (beenden mit Ctrl+C)", flush=True)
    if host_addr == "0.0.0.0":
        print("Achtung: im lokalen Netz erreichbar (z. B. vom Laptop auf den Raspberry Pi).")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        host.stop()
        httpd.server_close()
