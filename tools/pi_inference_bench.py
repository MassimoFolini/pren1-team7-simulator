#!/usr/bin/env python3
"""Misst die Rechenzeit der echten Erkennungs-Bausteine auf dem Raspberry Pi 5 (bzw. Laptop).

*** BISHER NICHT AUF ECHTER HARDWARE GETESTET *** (der Simulator selbst braucht diese Bibliotheken nicht).
Jeder Baustein wird nur gemessen, wenn seine Bibliothek installiert ist. Mit synthetischen Eingaben
(Rauschen), d. h. gemessen wird die Rechenlast, nicht die Erkennungsqualität.

Beispiele:
  python3 tools/pi_inference_bench.py --seconds 10
  python3 tools/pi_inference_bench.py --vosk-model ~/models/vosk-model-small-de-0.15 --yolo ~/models/best_ncnn_model
Ergebnisse in docs/RASPBERRY_PI.md (Tabelle «Messungen») eintragen.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import time


def have(m: str) -> bool:
    return importlib.util.find_spec(m) is not None


def timed(fn, seconds: float):
    n, t0 = 0, time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        fn()
        n += 1
    wall = time.perf_counter() - t0
    return {"calls": n, "ms_per_call": round(wall / max(n, 1) * 1000, 2), "fps": round(n / wall, 1)}


def bench_color_segmentation(seconds: float):
    """Plan B für die Knochenerkennung (MS2): Farbsegmentierung mit OpenCV, 640x480."""
    import cv2
    import numpy as np
    img = (np.random.rand(480, 640, 3) * 255).astype("uint8")

    def f():
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, (10, 30, 120), (35, 160, 255))
        cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return timed(f, seconds)


def bench_mediapipe_hands(seconds: float):
    import mediapipe as mp
    import numpy as np
    img = (np.random.rand(480, 640, 3) * 255).astype("uint8")
    with mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1) as h:
        return timed(lambda: h.process(img), seconds)


def bench_vosk(model_dir: str, seconds: float):
    import numpy as np
    import vosk
    model = vosk.Model(model_dir)
    rec = vosk.KaldiRecognizer(model, 16000, '["hier", "brav", "sitz", "such", "[unk]"]')
    audio = (np.random.randn(16000 * 5) * 800).astype("int16").tobytes()     # 5 s Rauschen
    t0 = time.perf_counter()
    for i in range(0, len(audio), 8000):
        rec.AcceptWaveform(audio[i:i + 8000])
    rec.FinalResult()
    wall = time.perf_counter() - t0
    return {"audio_s": 5.0, "wall_s": round(wall, 2), "real_time_factor": round(wall / 5.0, 3)}


def bench_yolo(path: str, seconds: float):
    import numpy as np
    from ultralytics import YOLO
    model = YOLO(path)
    img = (np.random.rand(480, 640, 3) * 255).astype("uint8")
    return timed(lambda: model.predict(img, imgsz=320, verbose=False), seconds)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10.0, help="Messdauer je Baustein")
    ap.add_argument("--vosk-model", default=None)
    ap.add_argument("--yolo", default=None, help="Modellpfad (z. B. NCNN-Export)")
    a = ap.parse_args()
    out = {"python": platform.python_version(), "machine": platform.machine(), "results": {}}
    jobs = []
    if have("cv2") and have("numpy"):
        jobs.append(("opencv_farbsegmentierung_640x480", lambda: bench_color_segmentation(a.seconds)))
    if have("mediapipe"):
        jobs.append(("mediapipe_hands_640x480", lambda: bench_mediapipe_hands(a.seconds)))
    if have("vosk") and a.vosk_model:
        jobs.append(("vosk_grammatik_4_woerter", lambda: bench_vosk(a.vosk_model, a.seconds)))
    if have("ultralytics") and a.yolo:
        jobs.append(("yolo_320px", lambda: bench_yolo(a.yolo, a.seconds)))
    for name, fn in jobs:
        try:
            out["results"][name] = fn()
        except Exception as e:          # noqa: BLE001
            out["results"][name] = {"fehler": repr(e)}
    skipped = [n for n, ok in [("opencv", have("cv2")), ("mediapipe", have("mediapipe")),
                               ("vosk (+ --vosk-model)", have("vosk") and a.vosk_model),
                               ("ultralytics (+ --yolo)", have("ultralytics") and a.yolo)] if not ok]
    out["nicht_gemessen"] = skipped
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
