# Bedienung der Weboberfläche

Start: `./run.sh` (Linux/macOS/Pi) bzw. `.\run.ps1` (Windows), dann `http://localhost:8080`.

## Aufbau

| Bereich | Inhalt |
|---|---|
| Kopfzeile | Verbindung, Simulationszeit, CPU-Last des Simulators, Pause, **Tempo** (0.5×–25×), Neustart, Hell/Dunkel |
| Links | **Schiedsrichter** (Sprache, Gesten, Start-Taster, **NOT-AUS**), **Umgebung** (Lärm, Licht, Abstand, knochenfarbener Boden), **Fehlerinjektion**, Knochen |
| Mitte | **Spielfeld** von oben: Startfeld, 30°-Suchsegment (5 m), Interaktionsbereich (R 1.5 m), Roboter mit Kamera-Sichtfeld und Distanzstrahl, Knochen, Schiedsrichter, wahre Spur (blau) und **Odometrie** (orange, zeigt den Drift) |
| Rechts | **Status** im Stil von Folie 8 (`command`, `robot_state`, `target`, `confidence`), **Zustandsautomat** (aktiver Zustand + letzter Übergang), Wahrnehmung, Mikrocontroller (Odometrie-Fehler, UART), Haltung (Seitenansicht), Energie |
| Unten | **Protokoll** (filterbar nach Quelle SBC/MCU/REFEREE/WORLD/OPERATOR), **Anforderungen** (live), **Szenarien**, **Tests**, **Info & Annahmen** |

## Typischer Ablauf von Hand

1. Warten bis `BEREIT` (Selbsttest ca. 2 s).
2. Gesten/Sprache auslösen (die Erkennung ist zufällig und hängt von Lärm, Licht und Abstand ab – genau das soll getestet werden).
3. `SUCH` sprechen (oder **Start-Taster**, falls die Sprache nicht erkannt wird) → DREHEN → SUCHEN → ANFAHREN → FUND_MELDEN → RUECKKEHR → BEREIT.
4. Tab «Anforderungen»: erfüllt/nicht erfüllt mit Messwert und Grenze.

## Tasten

`1` HIER · `2` BRAV · `3` SITZ · `4` SUCH · `5` Zusatzbefehl · `Q` Geste SITZ · `W` Geste PLATZ · `E` Geste AUF · `S` Start-Taster · `N` NOT-AUS · `Leertaste` Pause.

## Szenarien und Tests

* **Szenarien:** Tab «Szenarien» → ▶. Der Schiedsrichter arbeitet das Skript ab (wiederholt Befehle bei Nicht-Erkennung); am Ende «BESTANDEN/NICHT BESTANDEN» mit allen Prüfungen.
  Neue Szenarien: JSON in `scenarios/` ablegen (Format siehe [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md)).
* **Tests:** Sprach- und Gestenmatrix (Erkennungsrate je Wort/Geste nach Lärm bzw. Licht und Distanz, grün ≥ 90 %), Monte-Carlo (zufällige Suchläufe).
  Dieselben Auswertungen auf der Kommandozeile: `test-recognition`, `montecarlo`.

## Fehlerinjektion – was zeigt was?

| Schalter | Erwartetes Verhalten |
|---|---|
| Mikrofon ausgefallen | Sprache wird nicht erkannt; SUCH geht mit dem **Start-Taster** |
| Kamera ausgefallen | Keine Gesten/Knochen; kamerabasierte Berührung fällt aus |
| UART getrennt | MCU stoppt per Watchdog, Pi meldet «Verbindung verloren», erholt sich bei Wiederverbindung |
| Fühler an der Nase defekt | Berührung nur noch über die Kamera |
| Berührungserkennung (Kamera) defekt | Berührung nur über den Fühler |
| NOT-AUS | Räder sofort stromlos, Haltung eingefroren, `NOT_AUS`; danach «Taster entriegeln» → «Quittieren» |

## Fehlersuche

* Seite bleibt leer / «getrennt»: Server läuft nicht (Terminal prüfen) oder anderer Port (`--port`).
* Port belegt: `serve --port 8090`.
* Windows: `py -X utf8 -m pren_sim …` verwenden, falls Umlaute in der Konsole falsch erscheinen (`run.ps1` macht das schon).
