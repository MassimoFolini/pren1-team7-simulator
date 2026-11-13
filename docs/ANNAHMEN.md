# Annahmen und offene Fragen

Der Simulator setzt die Vorgaben so um, wie sie in der Aufgabenstellung (AS), der FAQ, der Besprechung KW41, der Rückmeldung MS1,
der Anforderungsliste V4 und dem MS2-Bericht stehen. Wo dort etwas **nicht festgelegt** ist, wurde eine Annahme getroffen.
Alle Werte stehen in `src/pren_sim/config.py` und lassen sich per `--config datei.json` oder in Szenarien (`"config": {…}`) ändern.

## A. Spielfeld und Ablauf

| # | Annahme | Quelle / Grund | Auswirkung |
|---|---|---|---|
| A1 | Suchsegment: Scheitel im Mittelpunkt des Startfelds, Achse in +x, 30°, Radius 5 m | Abb. 3 der AS liegt dem Simulator nicht vor; Folie 5: «30°-Segment, ca. 5 m» | Lage von Segment/Startfeld zueinander, Rückkehrweg |
| A2 | Startfeld 20 cm breit × 50 cm lang, Roboter steht mittig, Kopf in −x (weg vom Suchfeld) | AS Folie 5; FAQ 9 | Start- und Endlage |
| A3 | Interaktionsbereich R 1.5 m um den Startpunkt; Schiedsrichter 0.5–2 m vor dem Gesicht | KW41 (Radius), FAQ 14 (0.5–2 m) – die beiden Zahlen passen nicht ganz zusammen (2 m > 1.5 m) | Standard 1.5 m, einstellbar 0.5–2 m |
| A4 | Alle Knochen liegen im Segment; sonst ist ein Fund nicht möglich (FAQ 3: keine weiteren Gegenstände) | FAQ 3 | Detektionen ausserhalb werden verworfen |
| A5 | Wettbewerbs-Punktzahl nur als **Orientierung**: Grundbefehle je 10 P., Suche 40 P. linear nach Zeit | Folie 13 nennt nur die Maxima (40/40/20) | `checks.indicative_score` |
| A6 | Schiedsrichter-Geste wird 2.5 s gehalten, Befehl 0.6 s gesprochen | nicht vorgegeben | beeinflusst Erkennungsraten |

## B. Roboter

| # | Annahme | Wert |
|---|---|---|
| B1 | Abmasse (Skizze Differentialantrieb) | 41 cm lang, 17 cm breit, Spur 17 cm, Rad Ø 8 cm |
| B2 | Antrieb | v_max 0.6 m/s, ω_max 2.5 rad/s, Zeitkonstante 0.12 s, Encoder 1440 Ticks/Rad |
| B3 | Messfehler (erzeugen Odometrie-Drift) | Radius ±1.5 %, Spur ±2 %, Gyro-Bias ±0.05 °/s |
| B4 | Haltungswechsel | SITZ 1.2 s, PLATZ 1.8 s, AUF 1.5 s – MS3: Hebel/Drehmoment auslegen |
| B5 | Kamera | Standard-Blickwinkel 66° (Entscheid Team, MS2), tote Zone unter 0.30 m |
| B6 | Energie | 38.4 Wh (Stromversorgung-Recherche), Grundlast 10 W, Motoren bis 14 W, Servos 3–9 W |
| B7 | «Sofortiger Stopp» bei Not-Aus | ≤ 0.3 s (Anf. 7.1 nennt keine Zahl) |

## C. Erkennung (Platzhalter-Modelle)

Die Sensormodelle sind **keine Messergebnisse**. Sie sind so parametriert, dass sie plausibel und *testbar* sind (Erkennung nimmt mit Distanz und Lärm ab):

* Sprache: Sprechpegel 62 dB in 1 m, −6 dB pro Distanzverdopplung, Erkennungsrate = Sigmoid((SNR − 3 dB)/3.5). Bei 60 dB(A) Lärm und 1 m werden nur ca. 40 % der Befehle erkannt – das ist **eine Modellaussage**, die mit echtem Mikrofon-Array und Rauschunterdrückung zu überprüfen ist (Risiko «Spracherkennung im Lärm»).
* Gesten: Erkennung je Bild ca. 0.97 (0.5 m) bis 0.82 (2 m), skaliert mit Licht; Mehrheitsfilter 5 von 8 Bildern (der Filter ist der echte Brain-Code).
* Knochen: Detektionswahrscheinlichkeit sinkt quadratisch mit der Distanz (Reichweite 6 m), mit Licht und knochenfarbenem Boden.
* Berührung (TF22): Fühler an der Nase (zuverlässig) **und** kamerabasierte Erkennung (0.1 s Latenz, 90 %).

**Zu tun:** Sobald Mikrofon/Kamera vorhanden sind, Raten messen und die Modellparameter (`perception.py`) daran anpassen.

## D. Noch nicht entschieden (im Team klären)

1. **Zusatzbefehl / Kunststück** ist nicht definiert. Im Simulator: Platzhalter «KUNSTSTUECK» (Drehung 360°, Freude, ≤ 1 min), nur per Sprache. → Kunststück festlegen (Anf. 5.13).
2. **Spielfeld** (Klebeband, Material, Pylonen) ist laut Betreuer noch nicht definiert; der Roboter nutzt es deshalb **nicht** (Rückkehr nur per Odometrie).
3. **Abweichungen vom Zustandsdiagramm** (siehe [ARCHITEKTUR.md](ARCHITEKTUR.md)): Timeout über RUECKKEHR, Reset → BEREIT, Fehlerpfad Verbindungsverlust.
4. **Fahren rückwärts** ist nicht vorgesehen («Hund bewegt sich vorwärts»); beim Rückzug vom Knochen dreht der Roboter auf der Stelle (die Nase kann den Knochen dabei streifen).
5. **UART-Protokoll** (Baudrate, Prüfsumme) ist ein Vorschlag; bei Bedarf Prüfsumme ergänzen.
6. **«Alle Teams vollzählig anwesend»** (Input 7, TeamCoaching) – Organisatorisches, nicht Teil des Simulators.

## E. Bekannte Einschränkungen

* 2D-Modell: Haltung (Stand/Sitz/Platz) hat nur Zustand und Dauer; keine Dynamik der Beine, kein Kippen, keine Kollision mit dem Knochen (er wird nicht verschoben).
* Kein Audiosignal und kein Kamerabild: Wahrnehmung wird als Ereignisse/Wahrscheinlichkeiten modelliert (kein Test echter Algorithmen).
* Das Layout der Weboberfläche wurde mit Chromium (Desktop) geprüft; auf dem Pi-Bildschirm/Tablet nicht.
