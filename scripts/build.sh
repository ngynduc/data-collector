#!/usr/bin/env bash
# Build a single-file portable binary of telegram-collector with PyInstaller.
#
# Output: dist/telegram-collector (Linux/macOS) or dist\telegram-collector.exe (Windows, via build.ps1)
#
# Native deps:
#   cryptg is a compiled C extension. The binary is platform-locked:
#   a Linux build runs on Linux only, a Windows build runs on Windows only.
#   Build on the SAME OS you intend to run on.
#
# Usage:
#   bash scripts/build.sh            # default name: telegram-collector
#   APP_NAME=my-collector bash scripts/build.sh
#
# Prereq: pyinstaller installed in the active environment (uv pip install pyinstaller).

set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
APP_NAME="${APP_NAME:-telegram-collector}"

if ! "$PY" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "PyInstaller not found. Installing into current env..."
    "$PY" -m pip install --upgrade pyinstaller
fi

echo "Cleaning previous build artifacts..."
rm -rf build dist

echo "Building $APP_NAME (this takes a minute)..."
"$PY" -m PyInstaller \
    --onefile \
    --console \
    --name "$APP_NAME" \
    --collect-all telethon \
    --collect-all cryptg \
    --copy-metadata telegram_collector \
    --hidden-import "telethon.tl.types" \
    main.py

echo
echo "Done. Binary: dist/$APP_NAME"
echo "Verify:      ./dist/$APP_NAME --version"
echo
echo "Portable USB bundle = copy these together:"
echo "  dist/$APP_NAME      # the binary"
echo "  .env                # your API_ID / API_HASH"
echo "  *.session           # saved login (AUTH KEY - keep private / encrypt the USB)"
