#!/bin/bash
# Build both SVN Client and SVN Server Admin wheels.
# Automatically creates and uses the .venv virtual environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Bootstrap the virtual environment
source "$SCRIPT_DIR/ensure-venv.sh"

echo "=== Building SVN Client ==="
"$VENV_PYTHON" -m build "$ROOT_DIR/svn_client"

echo "=== Building SVN Server Admin ==="
"$VENV_PYTHON" -m build "$ROOT_DIR/svn_server"

echo "=== Build complete ==="
