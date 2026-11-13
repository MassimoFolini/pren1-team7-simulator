# PREN1 HS26 · Team 7 · Simulator / Digital Twin «Hunde-Roboter»

Simulator für den interaktiven Hunde-Roboter (HSLU PREN1 HS26), gebaut nach der in **Meilenstein 2** gewählten
**Variante V2 «Verteilte Architektur»**: Ein Einplatinenrechner (**Raspberry Pi 5**) übernimmt Wahrnehmung und
Zustandsautomat, ein **Mikrocontroller** (z. B. ESP32) alles Zeitkritische (Regelung, Servos, Not-Aus).
Der Simulator ersetzt die Hardware, damit die Software **unabhängig vom Roboter** entwickelt und kritische
Teilfunktionen schon in PREN1 getestet werden können (Aufgabenstellung Folie 8, Anf. 8.1, Rückmeldung MS1).

* **Läuft überall:** Windows, macOS, Linux und Raspberry Pi 5 – nur Python ≥ 3.10, **keine Pakete nötig**.
* **Komplett offline:** Weboberfläche ohne externe Bibliotheken/Schriften/Cloud (Anf. 4.2).
* **Gleiche Software wie am Roboter:** `brain.py` (Pi-Teil) und das UART-Textprotokoll bleiben beim Wechsel auf die echte Hardware unverändert (siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md)).

## Schnellstart

```bash
git clone <URL-dieses-Repos> Prenn && cd Prenn
```

| System | Befehl | Ergebnis |
|---|---|---|
| Windows (PowerShell) | `.\run.ps1` | startet den Server und öffnet `http://localhost:8080` |
| Linux / macOS / Raspberry Pi | `./run.sh` | startet den Server, dann `http://localhost:8080` öffnen |
| überall (ohne Skripte) | `PYTHONPATH=src python3 -m pren_sim serve` | wie oben (Windows: `$env:PYTHONPATH="src"`) |
| als Befehl installieren | `pip install -e .` → `pren-sim serve` | optional |

Weitere Befehle (jeweils `./run.sh <befehl>` bzw. `.\run.ps1 <befehl>`):

| Befehl | Zweck |
|---|---|
| `run --all` / `run 01_standardlauf -v` | Szenarien ohne Oberfläche durchlaufen, Anforderungen prüfen |
| `list` | vorhandene Szenarien |
| `test-recognition` | Erkennungsraten Sprache/Gesten nach Distanz, Lärm, Licht (Anf. 5.1–5.3, 13.2, 13.3) |
| `montecarlo -n 100` | viele zufällige Suchläufe (Anf. 6.2, 6.4, 6.6, 3.4) |
| `bench` | Rechenleistung messen (Pi 5 ↔ Laptop) |
| `serve --host 0.0.0.0` | im lokalen Netz erreichbar (z. B. Pi → Laptop-Browser) |

Tests: `python -m unittest discover -s tests -v` (25 Tests, ca. 3 s).

## Was der Simulator abbildet

```
 Schiedsrichter (Sprache, Gesten, Taster, Not-Aus)        Weboberfläche (Browser)
        │                                                        ▲  Zustand 20 Hz (SSE)
        ▼                                                        │
  Wahrnehmung (Modelle)  ──SensorFrame──▶  Brain [Pi 5]  ◀─UART-Text─▶  Firmware-Modell [MCU]
  Mikrofon · Kamera · Distanz              Arbitration                    PI-Regler · Odometrie
  Berührung                                Zustandsautomat                Watchdog · Not-Aus
                                           Suchstrategie                          │
                                           Quittierung                            ▼
                                                                  Strecke: Differentialantrieb,
                                                                  Haltungsaktor, Akku
```

* **Spielfeld** nach Aufgabenstellung: Startfeld 20×50 cm, 30°-Suchsegment mit 5 m, Interaktionsbereich R 1.5 m, Knochen 21 cm,
  Schiedsrichter 0.5–2 m *vor* dem Gesicht, Hund startet mit dem Rücken zum Suchbereich (FAQ 9, 14; Besprechung KW41).
* **Befehle:** Sprache HIER · BRAV · SITZ · SUCH, Gesten SITZ · PLATZ · AUF (AUF = Stand auf vier Beinen, FAQ 11), Zusatzbefehl (Kunststück, **Platzhalter**).
* **Ablauf SUCH:** Umdrehen → Suchen → Anfahren → Berühren → **sofort melden** (FAQ 12) → Rückkehr per Odometrie → sitzen; Abbruch nach 2 min.
* **Fehlerinjektion:** Störgeräusch, Licht, knochenfarbener Boden, Mikrofon/Kamera/Fühler defekt, UART getrennt, Not-Aus.
* **Anforderungsprüfung live:** jede Prüfung trägt die Nummer der Anforderungsliste V4 (Tab «Anforderungen»).
* **8 Szenarien** (JSON in [`scenarios/`](scenarios)): Standardlauf, Taster-Fallback, Not-Aus, Knochen am Rand, 60 dB Lärm, dunkel + knochenfarbener Boden, UART-Ausfall, Abbruch nach 2 min.

## Bedienung (Weboberfläche)

Links Schiedsrichter/Umgebung/Fehler, Mitte Spielfeld (Knochen und Schiedsrichter lassen sich ziehen, Doppelklick setzt den Knochen),
rechts Status wie auf Folie 8 der Aufgabenstellung, Zustandsautomat, Wahrnehmung, Mikrocontroller, Energie. Unten Protokoll,
Anforderungen, Szenarien, Tests, Info. Tasten: `1`–`5` Sprache, `Q W E` Gesten, `S` Start-Taster, `N` Not-Aus, `Leertaste` Pause.
Ausführlich: [docs/BEDIENUNG.md](docs/BEDIENUNG.md).

## Raspberry Pi 5

Installation, Autostart, Zugriff vom Laptop, Leistungsmessung und der Weg zu den echten Erkennungs-Bausteinen:
**[docs/RASPBERRY_PI.md](docs/RASPBERRY_PI.md)**.

## Projektstruktur

```
src/pren_sim/   config · geometry · world · plant (Strecke) · mcu (Firmware-Modell) · protocol · link
                perception (Sensormodelle) · brain (Pi-Software) · engine · checks · scenarios · experiments
                server · cli · bench · web/ (Oberfläche)
scenarios/      Szenarien als JSON (Schiedsrichter-Skript + Erwartungen)
tests/          Unit- und Szenariotests (unittest)
tools/          pi_inference_bench.py (Vosk/MediaPipe/YOLO auf dem Pi messen – noch ungetestet)
deploy/         systemd-Dienst, Kiosk-Autostart für den Pi
docs/           Architektur, Schnittstellen, Anforderungs-Zuordnung, Annahmen, Raspberry Pi, Bedienung
```

## Wichtig: Stand und Grenzen

Das ist die **erste lauffähige Version** (Anf. 8.2, MS3 am 04.12.2026). Die Sensor- und Antriebsmodelle sind **parametrische
Platzhalter** mit Annahmen des Teams, bis Messungen mit echter Hardware vorliegen – alle Annahmen und offenen Fragen
(Spielfeld-Geometrie, Kunststück, Punkteformel, …) stehen in **[docs/ANNAHMEN.md](docs/ANNAHMEN.md)**.
Die Erkennungsraten im Simulator sind deshalb **keine** Aussage über die echte Erkennungsqualität.

## Zusammenarbeit

Projektdokumentation, Anforderungsliste, Berichte und das gemeinsame Änderungslog liegen im Teams-Ordner
«PREN Team 7 – TM – Projektarbeit» (`CLAUDE.md`). Änderungen an diesem Repo bitte dort im Log vermerken.
