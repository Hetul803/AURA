#!/usr/bin/env bash
set -euo pipefail

TARGETS=(
  "/Applications/AURA.app"
  "$HOME/Library/Application Support/aura-desktop"
  "$HOME/Library/Logs/aura-desktop"
  "$HOME/.aura"
)

echo "AURA local reset"
echo "This removes the installed app and local AURA profile/cache/log data."
echo
printf 'Targets:\n'
for target in "${TARGETS[@]}"; do
  printf '  - %s\n' "$target"
done
echo

if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "Type RESET AURA to continue: " CONFIRM
  if [[ "$CONFIRM" != "RESET AURA" ]]; then
    echo "Reset cancelled."
    exit 0
  fi
fi

for target in "${TARGETS[@]}"; do
  if [[ -e "$target" ]]; then
    rm -rf "$target"
    echo "Removed: $target"
  else
    echo "Already absent: $target"
  fi
done

echo "AURA local reset complete."
