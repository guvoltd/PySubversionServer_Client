#!/bin/bash
# Build both SVN Client and SVN Server Admin wheels.
# Automatically creates and uses the .venv virtual environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Bootstrap the virtual environment
source "$SCRIPT_DIR/ensure-venv.sh"

# Vendor svn_shared/ into each app so the sdist/wheel builds are
# self-contained (sdist packaging can't reach outside the project directory
# to pick up the sibling svn_shared/ package).
bash "$SCRIPT_DIR/vendor-shared.sh"

echo "=== Building SVN Client ==="
"$VENV_PYTHON" -m build "$ROOT_DIR/svn_client"

echo "=== Building SVN Server Admin ==="
"$VENV_PYTHON" -m build "$ROOT_DIR/svn_server"

echo "=== Build complete ==="
