$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = $env:PYTHON
if (-not $Python) {
  $Python = "python"
}

Push-Location $Root
try {
  Write-Host "==> Private alpha readiness"
  & $Python "infra\scripts\private_alpha_check.py"

  Write-Host "==> Desktop packaging prerequisites"
  $node = Get-Command node -ErrorAction SilentlyContinue
  $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
  if (-not $node) {
    Write-Warning "node not found on PATH."
  } else {
    Write-Host "node: $($node.Source)"
  }
  if (-not $pnpm) {
    Write-Warning "pnpm not found; desktop install/build/package checks are skipped."
    exit 0
  }

  Write-Host "pnpm: $($pnpm.Source)"
  Push-Location "apps\desktop"
  try {
    pnpm test
    pnpm build
    pnpm package
  } finally {
    Pop-Location
  }
} finally {
  Pop-Location
}
