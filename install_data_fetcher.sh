#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting installation script..."
echo "Where should the virtual environment be set up?"
read -r venvpath

if [ -z "${venvpath}" ]; then
	venvpath="$SCRIPT_DIR"
fi

venvdir="$venvpath/.venv"

echo "Setting up Python virtual environment and installing dependencies..."
python3 -m venv "$venvdir"
"$venvdir/bin/python" -m pip install --upgrade pip
"$venvdir/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

echo "Virtual environment set up at $venvdir"
echo "Setup complete. Activate it with: source \"$venvdir/bin/activate\""
