# Hinweis für KI-Assistenten in diesem Repo

Dieses Repo enthält den Simulator des PREN1-Teams 7. Die Projektdokumentation, die verbindliche Logging-Regel und das **einzige** Änderungslog des Teams
liegen im Teams-Ordner `PREN Team 7 - TM - Projektarbeit` (Datei `CLAUDE.md`). Trage dort jede relevante Änderung am Simulator ein; lege hier kein eigenes Log an.

Kurzregeln für Änderungen:

* Zuerst `README.md` und `docs/ARCHITEKTUR.md` lesen. Annahmen stehen in `docs/ANNAHMEN.md` – neue Annahmen dort ergänzen.
* Nur Python-Standardbibliothek (Offline-Betrieb, Raspberry Pi); Weboberfläche ohne externe Ressourcen.
* `brain.py` darf weder `world`, `plant` noch den Simulator importieren (es muss unverändert am Roboter laufen).
* Vor dem Commit: `python -X utf8 -m unittest discover -s tests` und `PYTHONPATH=src python -X utf8 -m pren_sim run --all`.
* Quelle der Vorgaben: Anforderungsliste V4, MS2-Kurzbericht (V2), Aufgabenstellung, FAQ, Besprechung KW41 (alle im Teams-Ordner).
