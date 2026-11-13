# Betrieb auf dem Raspberry Pi 5

Der Simulator braucht **nur Python 3.10+** (Raspberry Pi OS «Bookworm» bringt 3.11 mit) und keine Pakete. Er läuft komplett offline.
Dadurch lässt sich auf dem Pi testen, ob die vorgesehene Rechenleistung reicht, bevor der Roboter gebaut wird (MS2: Pi 5 für Wahrnehmung + Zustandsautomat).

## 1. Installation

```bash
sudo apt update && sudo apt install -y git python3        # meist schon vorhanden
git clone <URL-dieses-Repos> ~/Prenn && cd ~/Prenn
./run.sh                       # Weboberfläche auf http://localhost:8080
```

Ohne Bildschirm am Pi (Zugriff vom Laptop im selben Netz):

```bash
./run.sh serve --host 0.0.0.0 --port 8080
# am Laptop: http://<IP-des-Pi>:8080   (IP: hostname -I)   oder   http://raspberrypi.local:8080
```

Hinweis: `--host 0.0.0.0` macht die Oberfläche im ganzen lokalen Netz sichtbar (es gibt keine Anmeldung). Nur im Team-/Labornetz verwenden.
Die Anforderung 4.2 (keine externe Datenverbindung) gilt für den **Betrieb des Roboters**; die Anzeige des Simulators darf lokal erfolgen (siehe MS2: «mit Dozierenden klären»).

## 2. Autostart (optional)

```bash
sudo cp deploy/pren-simulator.service /etc/systemd/system/      # Pfad/Benutzer in der Datei prüfen (Standard: /home/pi/Prenn)
sudo systemctl daemon-reload && sudo systemctl enable --now pren-simulator
journalctl -u pren-simulator -f
```

Vollbild am Pi-Bildschirm: `deploy/kiosk.desktop` nach `~/.config/autostart/` kopieren.

## 3. Leistung messen

```bash
./run.sh bench --seconds 120
```

Der Befehl misst (1) wie schnell der Simulator rechnet (Faktor gegenüber Echtzeit, Anteil eines Kerns bei 1×), (2) die Rechenzeit der einzelnen Teile
(Strecke, Firmware, Sensormodelle, Brain), (3) Temperatur und Drosselung des Pi (`vcgencmd`), (4) welche Erkennungs-Bibliotheken installiert sind.
Zum Vergleich auf dem Laptop und auf dem Pi ausführen und die Ergebnisse hier eintragen:

| Gerät | Datum | Simulator × Echtzeit | Anteil 1 Kern bei 1× | Brain-Tick (µs) | Bemerkung |
|---|---|---|---|---|---|
| Entwicklungs-Laptop (Windows 11, Python 3.12, AMD64) | 13.11.2026 | ca. 570× | ca. 0.2 % | ca. 2 | gemessen vom Assistenten |
| Raspberry Pi 5 | – | – | – | – | **noch zu messen** (Team) |

Erwartung (Schätzung, nicht gemessen): Der Simulator selbst ist leicht (bei 1× deutlich unter 5 % eines Kerns). Die eigentliche Last am Roboter entsteht durch die
**echten Erkennungs-Bausteine** – deshalb der nächste Schritt.

### Echte Erkennung messen (noch ungetestet)

`tools/pi_inference_bench.py` misst die Rechenzeit der in MS2 vorgesehenen Bausteine, sobald die Bibliotheken auf dem Pi installiert sind:

| Baustein (MS2) | Installation (Beispiel) | Aufruf |
|---|---|---|
| Sprache: Vosk mit Grammatik auf 4 Wörter + [unk] | `pip install vosk numpy` + kleines deutsches Modell | `--vosk-model <Ordner>` |
| Gesten: MediaPipe Hands | `pip install mediapipe` | automatisch |
| Knochen: Objektdetektor (z. B. YOLOv8n, NCNN) | `pip install ultralytics` + Modell | `--yolo <Modell>` |
| Plan B Knochen: Farbsegmentierung | `sudo apt install python3-opencv` | automatisch |

```bash
python3 tools/pi_inference_bench.py --seconds 10 --vosk-model ~/models/vosk-small-de --yolo ~/models/best_ncnn_model
```

Die Messung verwendet synthetische Eingaben (Rauschen): sie zeigt die **Rechenlast** (ms pro Bild, Echtzeitfaktor), nicht die Erkennungsqualität.
Kriterium für die Machbarkeit: Wahrnehmung (Gesten + Knochen + Sprache gleichzeitig) mit mindestens 10–15 Bildern/s und Echtzeitfaktor < 1 bei Sprache, **zusätzlich**
zum Brain (≈ 0.1 % Kern). Auch Temperatur (`vcgencmd measure_temp`, `get_throttled`) unter Dauerlast beobachten; der Pi 5 braucht Kühlung und ein 5 V/5 A-Netzteil.

## 4. Weg zur echten Hardware

1. UART: Pi-Pins (TXD/RXD, `/dev/serial0`, in `raspi-config` aktivieren) mit dem Mikrocontroller verbinden; `pip install pyserial`;
   `link.SerialLink` statt `SimLink` verwenden. Die Firmware setzt das Textprotokoll aus [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md) um.
2. Wahrnehmung: eine Klasse mit `read(now) -> SensorFrame` schreiben, die Mikrofon (Vosk), Kamera (MediaPipe, Detektor) und Distanzsensor einliest.
3. `brain.Brain(cfg, link, log)` wie im Simulator betreiben (Aufruf `tick(now, frame)` mit 20 Hz) – das Brain selbst bleibt unverändert.
4. Den Simulator weiter als Regressionstest einsetzen: jede Änderung am Brain muss `./run.sh run --all` und die Unit-Tests bestehen.

*Die Schritte 1–3 wurden noch nicht an echter Hardware ausprobiert.*
