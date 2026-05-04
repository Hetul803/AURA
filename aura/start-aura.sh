#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "AURA launcher"
echo "Repo app root: $ROOT"
echo "Starting developer mode from AURA/aura."
echo
exec bash "$ROOT/scripts/aura-dev.sh"
