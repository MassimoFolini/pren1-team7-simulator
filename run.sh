#!/usr/bin/env bash
# Simulator starten (Linux / macOS / Raspberry Pi OS). Keine Installation nötig, nur Python >= 3.10.
#   ./run.sh                    -> Weboberfläche auf http://localhost:8080
#   ./run.sh serve --host 0.0.0.0   -> auch vom Laptop aus erreichbar (Pi im lokalen Netz)
#   ./run.sh run --all          -> alle Szenarien ohne Oberfläche
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
if [ "$#" -eq 0 ]; then set -- serve; fi
exec python3 -X utf8 -m pren_sim "$@"
