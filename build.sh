#!/bin/bash

set -e  # exit immediately if anything fails

echo "Building uartterm..."

# Navigate to project root
cd "$(dirname "$0")"

# Run PyInstaller
rm -rf dist/uartterm build/uartterm
pyinstaller --onedir --name uartterm src/uartterm/cli.py

# Update symlink
sudo ln -sf "$(pwd)/dist/uartterm/uartterm" /usr/local/bin/uartterm

echo "uartterm build completed."