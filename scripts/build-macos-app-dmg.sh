#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements-dev.txt

pyinstaller --clean --noconfirm diskimage_explorer_x68k.spec

APP_PATH="dist/diskimage_explorer_x68k.app"
DMG_PATH="dist/diskimage_explorer_x68k-mac.dmg"

if [[ ! -d "$APP_PATH" ]]; then
  echo "ERROR: app bundle not found: $APP_PATH" >&2
  exit 1
fi

hdiutil create \
  -volname "diskimage_explorer_x68k" \
  -srcfolder "$APP_PATH" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Build complete: $APP_PATH"
echo "DMG complete: $DMG_PATH"
