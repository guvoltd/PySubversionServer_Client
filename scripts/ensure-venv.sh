#!/bin/bash
# ============================================================================
# ensure-venv.sh — Bootstrap and activate the project virtual environment.
#
# Creates .venv/ in the workspace root if it doesn't exist, installs core
# dependencies, and prints the path to the venv Python. Designed to be
# sourced by other scripts or called standalone.
#
# Usage (source — sets VENV_PYTHON, VENV_PIP, activates venv):
#   source scripts/ensure-venv.sh
#
# Usage (standalone — just prints venv python path):
#   scripts/ensure-venv.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$ROOT_DIR/.venv"

# ------------------------------------------------------------------
# Create venv if missing
# ------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "[venv] Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    echo "[venv] Created."
fi

# ------------------------------------------------------------------
# Resolve paths
# ------------------------------------------------------------------
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ------------------------------------------------------------------
# Install base dependencies if PySide6 is not yet installed
# ------------------------------------------------------------------
if ! "$VENV_PYTHON" -c "import PySide6" 2>/dev/null; then
    echo "[venv] Installing runtime dependencies (PySide6, keyring) ..."
    "$VENV_PIP" install --upgrade pip setuptools wheel -q
    "$VENV_PIP" install "PySide6>=6.7" "keyring>=25.0" -q
    echo "[venv] Runtime dependencies installed."
fi

# ------------------------------------------------------------------
# Install dev dependencies if pytest is not yet installed
# ------------------------------------------------------------------
if ! "$VENV_PYTHON" -c "import pytest" 2>/dev/null; then
    echo "[venv] Installing dev dependencies (pytest, ruff, mypy) ..."
    "$VENV_PIP" install "pytest>=8.0" "pytest-qt>=4.4" "pytest-cov>=5.0" "ruff>=0.4" "mypy>=1.10" -q
    echo "[venv] Dev dependencies installed."
fi

# ------------------------------------------------------------------
# Export for callers that source this script
# ------------------------------------------------------------------
export VENV_PYTHON
export VENV_PIP
export VENV_DIR
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"

# If run standalone (not sourced), print the python path
if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    echo "$VENV_PYTHON"
fi
