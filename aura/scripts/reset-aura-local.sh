#!/usr/bin/env bash
set -euo pipefail

TARGETS=(
  "/Applications/AURA.app"
  "$HOME/Library/Application Support/aura-desktop"
  "$HOME/Library/Logs/aura-desktop"
  "$HOME/.aura"
)

DELETE_MODE=0
YES_MODE=0
for arg in "$@"; do
  case "$arg" in
    --delete) DELETE_MODE=1 ;;
    --yes) YES_MODE=1 ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: scripts/reset-aura-local.sh [--yes] [--delete]"
      exit 1
      ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_DIR="$HOME/AURA_LOCAL_RESET_ARCHIVE_$STAMP"

echo "AURA local reset"
if [[ "$DELETE_MODE" == "1" ]]; then
  echo "This permanently removes the installed app and local AURA profile/cache/log data."
else
  echo "This moves the installed app and local AURA profile/cache/log data into:"
  echo "  $ARCHIVE_DIR"
fi
echo
printf 'Targets:\n'
for target in "${TARGETS[@]}"; do
  printf '  - %s\n' "$target"
done
echo

if [[ "$YES_MODE" != "1" ]]; then
  if [[ "$DELETE_MODE" == "1" ]]; then
    read -r -p "Type DELETE AURA to permanently delete local AURA state: " CONFIRM
    if [[ "$CONFIRM" != "DELETE AURA" ]]; then
      echo "Reset cancelled."
      exit 0
    fi
  else
    read -r -p "Type RESET AURA to archive local AURA state: " CONFIRM
    if [[ "$CONFIRM" != "RESET AURA" ]]; then
      echo "Reset cancelled."
      exit 0
    fi
  fi
fi

if [[ "$DELETE_MODE" != "1" ]]; then
  mkdir -p "$ARCHIVE_DIR"
fi

move_target() {
  local target="$1"
  local base
  base="$(basename "$target")"
  if [[ "$target" == "$HOME/Library/Application Support/aura-desktop" ]]; then
    mkdir -p "$ARCHIVE_DIR/Library/Application Support"
    mv "$target" "$ARCHIVE_DIR/Library/Application Support/$base"
  elif [[ "$target" == "$HOME/Library/Logs/aura-desktop" ]]; then
    mkdir -p "$ARCHIVE_DIR/Library/Logs"
    mv "$target" "$ARCHIVE_DIR/Library/Logs/$base"
  else
    mv "$target" "$ARCHIVE_DIR/$base"
  fi
}

for target in "${TARGETS[@]}"; do
  if [[ -e "$target" ]]; then
    if [[ "$DELETE_MODE" == "1" ]]; then
      rm -rf "$target"
      echo "Deleted: $target"
    else
      move_target "$target"
      echo "Archived: $target"
    fi
  else
    echo "Already absent: $target"
  fi
done

if [[ "$DELETE_MODE" != "1" ]]; then
  echo "Archive created: $ARCHIVE_DIR"
fi

echo "AURA local reset complete."
