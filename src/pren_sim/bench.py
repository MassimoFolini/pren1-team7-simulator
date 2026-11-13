"""Leistungsmessung für den Raspberry Pi 5 (und den Laptop zum Vergleich).

Misst: (1) Rechenzeit des Simulators und seiner Teile, (2) CPU-Temperatur/Drosselung (nur Raspberry Pi),
(3) ob optionale Erkennungs-Bibliotheken installiert sind. Echte Inferenz-Zeiten (Vosk, MediaPipe, Objektdetektor)
misst tools/pi_inference_bench.py, sobald die Bibliotheken auf dem Pi installiert sind.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import time

from .config import Config
from .engine import Simulation


def _vcgencmd(*args: str) -> str | None:
    exe = shutil.which("vcgencmd")
    if not exe:
        return None
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith(("model name", "model", "hardware")):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def run(sim_seconds: float = 120.0) -> dict:
    out: dict = {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
                 "cpu": cpu_model(), "cores": os.cpu_count()}
    temp0 = _vcgencmd("measure_temp")
    sim = Simulation(Config(), seed=1)
    sim.wait_ready()
    sim.place_bone(3.0, 0.4, 0.5)
    sim.say("SUCH")
    t0, c0 = time.perf_counter(), time.process_time()
    n0 = sim.n
    sim.run_for(sim_seconds)
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    steps = sim.n - n0
    out["simulation"] = {
        "sim_seconds": sim_seconds, "wall_seconds": round(wall, 2), "cpu_seconds": round(cpu, 2),
        "speed_x_realtime": round(sim_seconds / wall, 1), "steps_per_s": int(steps / wall),
        "cpu_load_at_1x_percent": round(100.0 * cpu / sim_seconds, 2),
        "note": "cpu_load_at_1x = Anteil eines Kerns, den der Simulator bei Echtzeit (1x) benötigt",
    }
    # Aufschlüsselung
    sim2 = Simulation(Config(), seed=2)
    sim2.wait_ready()
    reps = 3000
    t = time.perf_counter()
    for _ in range(reps):
        sim2.plant.step(0.01, sim2.t)
    t_plant = (time.perf_counter() - t) / reps
    t = time.perf_counter()
    for _ in range(reps):
        sim2.mcu.step(sim2.t, 0.01, False)
    t_mcu = (time.perf_counter() - t) / reps
    t = time.perf_counter()
    for _ in range(reps):
        sim2.sensors.read(sim2.t)
    t_sens = (time.perf_counter() - t) / reps
    fr = sim2.sensors.read(sim2.t)
    t = time.perf_counter()
    for _ in range(reps):
        sim2.brain.tick(sim2.t, fr)
    t_brain = (time.perf_counter() - t) / reps
    out["per_call_us"] = {"plant_step_100hz": round(t_plant * 1e6, 1), "mcu_step_100hz": round(t_mcu * 1e6, 1),
                          "sensors_20hz": round(t_sens * 1e6, 1), "brain_tick_20hz": round(t_brain * 1e6, 1)}
    t = time.perf_counter()
    import json
    for _ in range(200):
        json.dumps(sim.snapshot(0))
    out["snapshot_json_ms"] = round((time.perf_counter() - t) / 200 * 1000, 2)
    # Raspberry Pi: Temperatur und Drosselung
    pi = {"temp_before": temp0, "temp_after": _vcgencmd("measure_temp"), "throttled": _vcgencmd("get_throttled")}
    out["raspberry_pi"] = pi if any(pi.values()) else "nicht erkannt (vcgencmd fehlt) – Messung auf dem Laptop"
    # optionale Bibliotheken
    mods = ["numpy", "cv2", "vosk", "mediapipe", "ultralytics", "ncnn", "tflite_runtime", "picamera2", "serial", "sounddevice"]
    out["optional_libraries"] = {m: importlib.util.find_spec(m) is not None for m in mods}
    return out
