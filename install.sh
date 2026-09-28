#!/usr/bin/env bash
# Universal installer for UAPorter (Linux & macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "[UAPorter] Setting up Python virtual environment..."
python3 -m venv "$SCRIPT_DIR/.venv"
"$SCRIPT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$SCRIPT_DIR/.venv/bin/pip" install --quiet -e "$SCRIPT_DIR"

mkdir -p "$BIN_DIR"
ln -sf "$SCRIPT_DIR/.venv/bin/uaporter" "$BIN_DIR/uaporter"

echo "[UAPorter] Installation complete!"
echo "[UAPorter] You can now run 'uaporter --help' from any terminal."
