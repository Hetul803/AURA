$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$Python = $env:PYTHON
if (-not $Python) {
  $Python = "python"
}

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Command
  )
  Write-Host "==> $Name"
  & $Command
}

Push-Location $Root
try {
  Invoke-Step "Backend tests" {
    & $Python -m pytest "aura\apps\backend\tests" -q
  }

  Invoke-Step "Backend compile check" {
    & $Python -m compileall -q "aura\apps\backend\src"
  }

  Invoke-Step "Private alpha readiness" {
    & $Python "aura\infra\scripts\private_alpha_check.py"
  }

  $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
  if ($pnpm) {
    Invoke-Step "Desktop renderer tests" {
      Push-Location "aura\apps\desktop"
      try {
        pnpm test
      } finally {
        Pop-Location
      }
    }

    Invoke-Step "Desktop build sanity" {
      Push-Location "aura\apps\desktop"
      try {
        pnpm build
      } finally {
        Pop-Location
      }
    }

    Invoke-Step "Web tests" {
      Push-Location "aura\apps\web"
      try {
        $env:NODE_ENV = "test"
        pnpm test
      } finally {
        Pop-Location
      }
    }
  } else {
    Write-Warning "pnpm not found; skipped desktop/web tests and builds."
  }
} finally {
  Pop-Location
}
