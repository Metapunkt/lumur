#!/usr/bin/env bash
# Import the Lumur Godot project so class_name / global class cache exists.
# Fresh checkouts fail GDScript parse until this runs once (Godot 4.x).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT="${GODOT_BIN:-}"

if [[ -z "$GODOT" ]]; then
  if [[ -x "$ROOT/tools/godot" ]]; then
    GODOT="$ROOT/tools/godot"
  elif command -v godot >/dev/null 2>&1; then
    GODOT="$(command -v godot)"
  elif command -v godot4 >/dev/null 2>&1; then
    GODOT="$(command -v godot4)"
  else
    echo "godot_import: no Godot binary (set GODOT_BIN or install godot)" >&2
    exit 2
  fi
fi

cd "$ROOT"
echo "godot_import: using $GODOT" >&2

# Prefer --import (Godot 4.2+). Fall back to editor quit which also writes .godot/.
if "$GODOT" --help 2>&1 | grep -q -- '--import'; then
  "$GODOT" --headless --path "$ROOT" --import
else
  "$GODOT" --headless --path "$ROOT" --editor --quit
fi

if [[ ! -d "$ROOT/.godot" ]]; then
  echo "godot_import: expected .godot/ after import" >&2
  exit 1
fi
echo "godot_import: ok (.godot present)" >&2
