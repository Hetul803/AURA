#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Aegisure launcher"
echo "Repo app root: $ROOT"
echo "Starting developer mode from Aegisure/aegisure."
echo
exec bash "$ROOT/scripts/aura-dev.sh"
