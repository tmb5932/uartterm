#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_PATH="$SCRIPT_DIR/uartterm"

if [ ! -f "$BIN_PATH" ]; then
  echo "uartterm executable not found."
  exit 1
fi

chmod +x "$BIN_PATH"
sudo mkdir -p /usr/local/bin
sudo cp "$BIN_PATH" /usr/local/bin/uartterm

echo "Installed uartterm to /usr/local/bin/uartterm"
echo "Installation complete. Restart any existing terminals to use the new command."
echo "Run it in any terminal with: uartterm"