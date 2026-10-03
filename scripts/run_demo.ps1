# Start SeaWatch (API + web UI) for the demo.  Usage:  .\scripts\run_demo.ps1
# Opens two windows (API on :8000, web on :5173) and the browser.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "apps/web/node_modules")) {
    Write-Host "Installing web dependencies (first run only)..."
    Push-Location apps/web; npm install; Pop-Location
}
if (-not (Test-Path "data/models/detection_ml.joblib")) {
    Write-Host "Tip: run 'python scripts/train_detection_ml.py' once to enable the ML second opinion (takes ~2-3 min)."
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; python -m uvicorn apps.api.seawatch.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root/apps/web'; npm run dev"
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
