# Starts the backend (port 8000) and the frontend (port 3000) together.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
# First time: create the backend virtualenv and install both projects (see README.md).
$root = Split-Path -Parent $PSScriptRoot

$backend = Join-Path $root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "Backend venv missing. Run: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"; exit 1 }

Write-Host "Starting backend on http://localhost:8000 ..."
# --host 127.0.0.1: the API has no login, so it must only listen on this computer, never on the network
Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backend -WindowStyle Hidden

$frontend = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $frontend ".env.local"))) {
  "NEXT_PUBLIC_API_URL=http://localhost:8000" | Out-File -Encoding ascii (Join-Path $frontend ".env.local")
  Write-Host "Created frontend\.env.local (live mode)."
}
Write-Host "Starting frontend on http://localhost:3000 ..."
Set-Location $frontend
# webpack works everywhere, including machines where Next's native compiler is blocked
npm run dev:webpack
