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

## 3D-Ansicht und Roboter-Kamera

Oben im Spielfeld zwischen **2D** und **3D** umschalten. In 3D: **Übersicht** (Maus ziehen = drehen, Rad = Zoom, Shift/Rechtsklick = verschieben),
**Folgen** (hinter dem Roboter) und **Roboter-Kamera** (Sicht der Kamera gross). In den anderen Ansichten läuft die Kamera als Bild im Bild mit.
Das Kamerabild zeigt, was die Wahrnehmung «sieht»: **grüne Box** = erkannter Knochen mit Konfidenz und Distanz, **grau gestrichelt** = Knochen im Bild, aber nicht erkannt.
Der Regler «Raumlicht» macht Szene und Kamerabild dunkler, «Boden knochenfarben» färbt den Boden. Haltungen (Stand/Sitz/Platz), Räder, Schwanz und die Gesten des
Schiedsrichters (Arm) sind animiert. Die 3D-Ansicht braucht WebGL (jeder aktuelle Browser, auch Chromium auf dem Pi 5); three.js liegt lokal im Repo (MIT-Lizenz), kein Internet nötig.

## Live-Sprachbefehle mit dem Mikrofon

Links «🎤 Mikrofon einschalten» (Taste `M`), Browser-Berechtigung erlauben und **HIER, BRAV, SITZ, SUCH** (oder «Kunststück») sprechen.
Das erkannte Wort geht durch dieselbe Brain-Logik wie alles andere (Konfidenzschwelle 0.6, Sperrzeit, nur im passenden Zustand). Gesten (SITZ, PLATZ, AUF)
lassen sich nicht sprechen: dafür die Gesten-Knöpfe nutzen.

* Technik: Web Speech API (Chrome/Edge). **Achtung:** Der Browser schickt den Ton an einen **Online-Dienst** des Browser-Anbieters. Das ist nur eine Komfortfunktion des Simulators und
  widerspricht dem Offline-Grundsatz nur für den Simulator, nicht für den Roboter (dort lokale Erkennung, z. B. Vosk).
* Funktioniert nur auf `http://localhost` (sicherer Kontext). Vom Laptop auf den Pi per IP-Adresse blockiert der Browser das Mikrofon; dann den Browser auf dem Pi selbst nutzen.
* Ohne Internet oder in Firefox ist die Funktion nicht verfügbar; alles andere läuft weiter.
* Zwischenergebnisse haben oft keine echte Konfidenz; dafür wird 0.8 angenommen, bei fertigen Ergebnissen die Konfidenz des Browsers.

## Tasten

`1` HIER · `2` BRAV · `3` SITZ · `4` SUCH · `5` Zusatzbefehl · `M` Mikrofon · `Q` Geste SITZ · `W` Geste PLATZ · `E` Geste AUF · `S` Start-Taster · `N` NOT-AUS · `Leertaste` Pause.

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
