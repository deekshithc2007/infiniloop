# Convenience script to run HeatWise AI Backend + Frontend locally on Windows
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$nodeDir = "$env:LOCALAPPDATA\Programs\nodejs"
if (Test-Path $nodeDir) {
  $env:PATH = "$nodeDir;" + $env:PATH
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; `$env:PATH = '$nodeDir;' + `$env:PATH; npm run dev"
Write-Host "HeatWise AI starting: Backend at http://127.0.0.1:8000/docs | Frontend at http://localhost:5173"
