# Schnittstellen

## 1. UART-Textprotokoll Pi ↔ Mikrocontroller (`protocol.py`)

Eine Zeile = ein Telegramm, Felder durch Leerzeichen, Abschluss `\n`, 115200 Baud (Vorschlag). Zahlen mit Punkt, SI-Einheiten.
Entspricht der Festlegung im MS2-Bericht («einfache Textbefehle über UART, z. B. DRIVE v ω, POSE SITZ»).

### Pi → MCU

| Telegramm | Bedeutung | Antwort/Wirkung |
|---|---|---|
| `DRIVE <v m/s> <w rad/s>` | Fahrbefehl, **muss alle ≤ 0.5 s erneuert werden** | Watchdog stoppt sonst; nur im Stand (`ERR POSE`) und ohne Not-Aus (`ERR ESTOP`); `DRIVE 0 0` immer erlaubt |
| `STOP` | Räder anhalten (ohne Latch) | |
| `POSE STAND\|SITZ\|PLATZ` | Haltung wechseln | `POSE …` Telemetrie; `ERR MOVING`, wenn der Roboter noch fährt |
| `SHOW HAPPY\|SPIN\|TAIL` | Ausdruck (Schwanz/Ohren/Augen) | |
| `PING` | Lebenszeichen | `PONG` (hält die Fahr-Überwachung **nicht** wach) |
| `ESTOP` | Software-Not-Aus (Latch) | `EVT ESTOP sw` |
| `ESTOP_RESET` | Not-Aus quittieren | nur wenn Hardware-Taster entriegelt (`ERR ESTOP`), sonst `EVT ESTOP_CLEARED` |
| `ODOM_RESET` | Odometrie auf Startpose setzen | |

### MCU → Pi

| Telegramm | Rate | Bedeutung |
|---|---|---|
| `ODOM x y th v w` | 20 Hz | Pose aus Encoder + Gyro (Meter, rad), Soll-Geschwindigkeiten |
| `POSE <STAND\|SITZ\|PLATZ\|MOVING> <DONE\|BUSY>` | 20 Hz | Haltung |
| `BAT <soc 0..1> <Wh verbraucht>` | 2 Hz | Akku |
| `EVT TOUCH` | Ereignis | Fühler an der Nase berührt (Knochen) |
| `EVT BTN_START` | Ereignis | Start-Taster (Fallback für SUCH, Anf. 6.5) |
| `EVT ESTOP hw\|sw` / `EVT ESTOP_CLEARED` | Ereignis | Not-Aus ausgelöst / quittiert |
| `EVT WDG` | Ereignis | Watchdog hat gestoppt |
| `ERR <code> [text]` | Ereignis | `POSE`, `ESTOP`, `MOVING`, `SYNTAX`, `ARG` |

Sicherheitsregeln der Firmware: Hardware-Not-Aus wirkt sofort **ohne** den Rechner; Räder stromlos, Haltung eingefroren; Fahren nur im Stand;
Watchdog 0.5 s; Quittieren nur bei entriegeltem Taster.

## 2. Wahrnehmung → Brain (`perception.SensorFrame`)

| Feld | Inhalt |
|---|---|
| `keywords` | Liste `KeywordEvent(word, conf, t)`; Wort ∈ {HIER, BRAV, SITZ, SUCH, Zusatzbefehl, `[unk]`} |
| `gesture` | `(Label, Konfidenz)` oder `None` – **pro Kamerabild**; der Mehrheitsfilter sitzt im Brain (`brain.vote_gesture`) |
| `bone` | `Detection(bearing rad links+, dist m, conf)` oder `None` |
| `tof` | Distanz des Einpunktsensors in m oder `None` |
| `touch_cam` | kamerabasierte Berührungserkennung (TF22) |

Eine echte Implementierung liefert dieselben Felder (`hal.SensorSource.read(now)`).

## 3. HTTP-API des Simulators (`server.py`)

Alles JSON, Standard `http://localhost:8080`. Zugriff nur lokal, ausser `--host 0.0.0.0`.

| Methode, Pfad | Body | Wirkung |
|---|---|---|
| `GET /api/stream` | – | Server-Sent-Events: vollständiger Zustand 20 Hz |
| `GET /api/state` | – | Zustand einmalig (inkl. Spuren) |
| `GET /api/scenarios`, `/api/config`, `/api/fsm`, `/api/info`, `/api/jobs` | – | Szenarien, Konfiguration, Zustandsautomat, Systeminfo, Auswertungen |
| `POST /api/say` | `{"word":"SUCH"}` | Schiedsrichter spricht |
| `POST /api/gesture` | `{"name":"SITZ"}` | Schiedsrichter zeigt Geste (2.5 s) |
| `POST /api/button` / `estop` / `estop_release` / `estop_reset` | – | Start-Taster, Not-Aus, Entriegeln, Quittieren |
| `POST /api/env` | z. B. `{"noise_db":60,"light_lux":80,"referee_distance":2.0,"floor_similarity":0.5,"mic_ok":false,"link_ok":false}` | Umgebung / Fehlerinjektion |
| `POST /api/bone` | `{"x":3,"y":0.4,"th":0.5}` oder `{"random":true}` | Knochen setzen |
| `POST /api/sim` | `{"speed":5,"paused":false}` / `{"reset":true,"seed":7}` | Tempo, Pause, Neustart |
| `POST /api/scenario` | `{"id":"01_standardlauf","seed":7}` | Szenario starten |
| `POST /api/test/voice` / `gesture` / `montecarlo` | `{"n":200}` | Auswertung im Hintergrund, Ergebnis in `GET /api/jobs` |

## 4. Szenario-Format (`scenarios/*.json`)

```json
{
  "title": "…", "description": "…", "seed": 7,
  "env": {"noise_db": 45, "light_lux": 500, "referee_distance": 1.5},
  "bone": {"x": 3.1, "y": 0.45, "th": 0.5},
  "required": ["6.4", "3.4/3.5"],
  "steps": [
    {"do": "gesture", "name": "SITZ", "expect": {"pose": "SITZ"}, "timeout": 7, "retries": 3},
    {"do": "say", "word": "SUCH", "expect": {"event": "search_start"}, "retries": 3},
    {"do": "wait_event", "event": "run_complete", "timeout": 150}
  ]
}
```

Schritte: `say`, `gesture`, `button`, `estop`, `estop_release`, `reset`, `env`, `place_bone`, `wait`, `wait_event`.
`expect`: `pose`, `state`, `cmd`, `event` (UND-verknüpft). `retries`: Der Schiedsrichter wiederholt den Befehl, falls er nicht erkannt wird
(die Anzahl Versuche wird ausgewertet). `optional`: Fehlschlag zählt nicht. `required`: nur diese Anforderungen müssen bestanden sein
(sonst darf keine Prüfung `fail` sein).
