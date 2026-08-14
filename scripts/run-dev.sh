#!/bin/bash
# Run either the SVN Client or SVN Server Admin in development mode.
# Automatically creates and uses the .venv virtual environment.
#
# Usage: ./scripts/run-dev.sh client
#        ./scripts/run-dev.sh server
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Bootstrap the virtual environment (creates .venv if missing, installs deps)
source "$SCRIPT_DIR/ensure-venv.sh"

export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

case "${1:-}" in
    client)
        echo "Starting SVN Client (using $VENV_PYTHON) ..."
        "$VENV_PYTHON" -m svn_client
        ;;
    server)
        echo "Starting SVN Server Admin (using $VENV_PYTHON) ..."
        "$VENV_PYTHON" -m svn_server
        ;;
    *)
        echo "Usage: $0 {client|server}"
        exit 1
        ;;
esac
