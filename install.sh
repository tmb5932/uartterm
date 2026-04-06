#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/dist/uartterm/uartterm"

if [ ! -f "$APP_PATH" ]; then
  echo "uartterm executable not found at: $APP_PATH"
  exit 1
fi

sudo mkdir -p /usr/local/bin
sudo ln -sf "$APP_PATH" /usr/local/bin/uartterm

echo "Installed symlink:"
ls -l /usr/local/bin/uartterm
echo "Any existing terminals must be closed."
echo "Run it with: uartterm"