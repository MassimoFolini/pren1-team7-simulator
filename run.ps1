# Simulator starten (Windows). Keine Installation nötig, nur Python >= 3.10.
#   .\run.ps1                 -> Weboberfläche auf http://localhost:8080
#   .\run.ps1 run --all       -> alle Szenarien ohne Oberfläche
#   .\run.ps1 test-recognition
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
if ($args.Count -eq 0) { & $py -X utf8 -m pren_sim serve --open } else { & $py -X utf8 -m pren_sim @args }
