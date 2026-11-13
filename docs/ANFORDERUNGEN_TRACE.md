# Zuordnung Anforderungen → Simulator

Basis: **Anforderungsliste V4** (Nummerierung Kategorie.Nr.), Aufgabenstellung HS26 (AS), FAQ v02, Besprechung KW41, Rückmeldung MS1.
«Prüfung» = automatische Prüfung in `checks.py` (Tab «Anforderungen»). Grenzwerte ohne Zahl in der Anforderungsliste sind **Annahmen**.

| Anf. | Anforderung | Im Simulator | Prüfung / Test | Stand |
|---|---|---|---|---|
| 1.1, 1.2 | Abmasse 20×50×50 cm, 1 m Länge | `RobotConfig.length/width` (41 × 17 cm) | `test_werte_aus_aufgabenstellung` | geprüft (Konfiguration) |
| 2.1 | Gewicht ≤ 7 kg | – | – | nicht Teil des Simulators |
| 3.1 | Autonom | kompletter Ablauf ohne Eingriff | Szenario 01 | ✔ |
| 3.3 | Umdrehen zum Suchfeld (Kopf voran fahren) | Zustand DREHEN, Start mit Rücken zum Feld | Check 3.3/5.7, `test_umdrehen_…` | ✔ |
| 3.4 | Rückkehr ins Startfeld ohne Klebeband | Odometrie (Encoder + Gyro) mit Drift | Check 3.4/3.5 (≤ 10 cm), Szenario 01, 04, 08, Monte-Carlo | ✔ |
| 3.5 | Endposition sitzend im Startfeld | POSE SITZ nach Rückkehr | Check 3.4/3.5 | ✔ |
| 4.2 | keine externe Datenverbindung | Weboberfläche ohne externe Ressourcen, Server nur lokal | Check 4.2 | ✔ |
| 4.3 | Akku-Laufzeit ≥ 12 min | Leistungsmodell, Hochrechnung | Check 4.3 | Modell (Annahme) |
| 5.1 | 4 Sprachbefehle erkennen | Sprachmodell (SNR, Latenz, Verwechslung) | `test-recognition`, Szenario 05 | Modell (Platzhalter) |
| 5.2 | 3 Gesten erkennen | Gestenmodell + Mehrheitsfilter | `test-recognition` | Modell (Platzhalter) |
| 5.3 | Distanz 0.5–2 m | `referee_distance` einstellbar | Matrix 0.5/1/2 m | ✔ |
| 5.4 | Interaktionsbereich R 1.5 m | im Spielfeld dargestellt | – | Darstellung |
| 5.5 | jeden Befehl quittieren | `Brain.ack` (Ton/LED/Augen) | Check 5.5 (≤ 0.5 s, Annahme) | ✔ |
| 5.6 | HIER: auf die Person zu | Zustand HIER mit Distanzsensor | Check 5.6 (≥ 0.3 m, Annahme) | ✔ |
| 5.7 | SUCH startet Suche, Umkehr | DREHEN → SUCHEN | Check 3.3/5.7 | ✔ |
| 5.8 | BRAV: Emotion | `SHOW HAPPY` | Check 5.8 | ✔ |
| 5.9–5.12 | SITZ (Sprache/Geste), PLATZ, AUF (= Stand) | Haltungsaktor, Zustand PLATZ | Checks 5.9–5.12, Szenario 01 | ✔ |
| 5.13 | Zusatzbefehl ≤ 1 min | **Platzhalter**-Kunststück (Drehung + Freude) | Check 5.13 | Platzhalter – Kunststück nicht definiert |
| 6.1 | Suchbereich 30°, 5 m | Segment, Knochen zufällig darin | Monte-Carlo | ✔ (Annahme Achse/Scheitel) |
| 6.2 | Knochen erkennen und auffinden | Detektormodell, Suchstrategie | Check 6.2/6.3, Monte-Carlo | Modell |
| 6.3 | Knochen berühren | Fühler + kamerabasierte Berührung (TF22) | Check 6.2/6.3, `touch_*` Fehlerinjektion | ✔ |
| 6.4 | Fund am Ort/Zeitpunkt der Berührung melden | `found` sofort bei `EVT TOUCH` | Check 6.4 (≤ 1 s, Annahme) | ✔ |
| 6.5 | Start per Taster als Backup | `EVT BTN_START` | Check 6.5, Szenario 02 | ✔ |
| 6.6 | Suche ≤ 2 min | Timeout 120 s → Rückkehr | Check 6.6, Szenario 08 | ✔ |
| 7.1 | Not-Aus jederzeit | Hardware-Not-Aus im MCU-Modell | Check 7.1 (≤ 0.3 s, Annahme), Szenario 03 | ✔ |
| 7.3 | Spielfeld nicht verändern; im Feld bleiben (FAQ 6) | Verwerfen von Detektionen ausserhalb; Feldverlassen wird gezählt | Check 7.3/FAQ6 | ✔ |
| 8.1 | Digital Twin / Simulator | dieses Projekt | Demo/Review mit Betreuer | **erste Version** |
| 8.2 | lauffähige Version bis Ende PREN1 | `./run.sh` | Demo MS3 (04.12.2026) | **erste Version** |
| 13.1 | Umgebung Innenraum, 15–30 °C | – | – | nicht modelliert |
| 13.2 | Licht 200–1000 lx | `light_lux` wirkt auf Gesten/Knochen | Matrix, Szenario 06 | Modell |
| 13.3 | Störgeräusch bis ca. 60 dB(A) | `noise_db` wirkt auf Sprache | Matrix, Szenario 05 | Modell |

Nicht im Simulator (Hardware): 1.3, 2.2, 4.1, 7.2, 9.x, 10.x, 11.x, 12.x.

## Bezug zu Input «Funktionsmuster / Testing» (16.10.2026)

Der Simulator dient als **virtuelles Modell / Digital Twin** (Input Folie 9, 13: «Simulator/Test» im V-Modell) und prüft kritische Funktionen
mit **messbarem Resultat**: Erkennungsraten (Matrix), Suchzeit, Meldeverzug, Rückkehrfehler, Stoppzeit, Laufzeit (Monte-Carlo, Szenarien).
Gemäss MS1-Rückmeldung 14 («Kritische Funktionen können/sollen bereits in PREN1 getestet werden») ist das die Grundlage für Gantt Nr. 20.
