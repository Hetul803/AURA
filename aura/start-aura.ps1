$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Require-Command($Name, $Help) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Error "Missing $Name. $Help"
  }
}

Require-Command node "Install Node.js 20 LTS or newer."
Require-Command pnpm "Install pnpm with: corepack enable pnpm  OR  npm install -g pnpm"
Require-Command python "Install Python 3.10+ and ensure python is on PATH."

$major = [int]((node -p "process.versions.node").Split(".")[0])
if ($major -lt 18) {
  throw "AURA needs Node.js 18+; found $(node -v). Install Node.js 20 LTS or newer."
}

if (-not (Test-Path "node_modules") -or -not (Test-Path "apps\desktop\node_modules")) {
  Write-Host "==> Installing pnpm workspace dependencies"
  pnpm install
}

Write-Host "==> Rebuilding Electron/esbuild"
pnpm rebuild electron esbuild
pnpm aura:verify-electron

if (-not (Test-Path "apps\backend\.venv\Scripts\python.exe")) {
  Write-Host "==> Creating backend virtual environment"
  python -m venv "apps\backend\.venv"
}

Write-Host "==> Installing backend dependencies"
& "apps\backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "apps\backend\.venv\Scripts\python.exe" -m pip install -e "apps\backend"

$port = if ($env:AURA_BACKEND_PORT) { $env:AURA_BACKEND_PORT } else { "8000" }
$backendUrl = "http://127.0.0.1:$port"

try {
  Invoke-WebRequest "$backendUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
  Write-Host "==> AURA backend already running at $backendUrl"
  $backendProcess = $null
} catch {
  Write-Host "==> Starting AURA backend at $backendUrl"
  $backendProcess = Start-Process -FilePath "apps\backend\.venv\Scripts\python.exe" -ArgumentList @("-m", "uvicorn", "api.main:app", "--app-dir", "apps/backend/src", "--host", "127.0.0.1", "--port", $port) -PassThru -NoNewWindow
}

for ($i = 0; $i -lt 40; $i++) {
  try {
    Invoke-WebRequest "$backendUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
    break
  } catch {
    Start-Sleep -Milliseconds 250
  }
}

try {
  Invoke-WebRequest "$backendUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
} catch {
  if ($backendProcess) { Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue }
  throw "Backend did not become healthy at $backendUrl. Run pnpm aura:backend to inspect logs."
}

Write-Host "==> Starting AURA desktop"
$env:AURA_BACKEND_URL = $backendUrl
pnpm --filter aura-desktop dev
