#!/bin/bash
# vendor-shared.sh — Copy svn_shared/ into each app package directory.
#
# Purpose:
#   Makes each app package self-contained so it can be built as a standalone
#   wheel without relying on the sibling svn_shared/ directory at runtime.
#   After vendoring, remove the PYTHONPATH=. workaround from launch commands.
#
# What it does:
#   1. Removes any previously vendored copy of svn_shared/ from each app.
#   2. Copies the current svn_shared/ source tree into each app directory.
#   3. Patches each app's pyproject.toml packages.find.include to include
#      the vendored svn_shared in the wheel.
#
# Environment variables:
#   VENDOR_TARGETS    Space-separated list of app dirs (default: svn_client svn_server)
#   VENDOR_DEST_NAME  Name of the vendored subdirectory (default: svn_shared)
#
# Usage:
#   bash scripts/vendor-shared.sh          # vendor into both apps
#   VENDOR_TARGETS=svn_client bash scripts/vendor-shared.sh   # client only
#
# After vendoring, rebuild your wheels:
#   python -m build svn_client
#   python -m build svn_server

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

TARGETS="${VENDOR_TARGETS:-svn_client svn_server}"
DEST_NAME="${VENDOR_DEST_NAME:-svn_shared}"
SRC="${ROOT_DIR}/svn_shared"

if [ ! -d "${SRC}" ]; then
    echo "ERROR: svn_shared/ not found at ${SRC}" >&2
    exit 1
fi

echo "=== Vendoring ${SRC} into: ${TARGETS} ==="

for target in ${TARGETS}; do
    TARGET_DIR="${ROOT_DIR}/${target}"
    DEST="${TARGET_DIR}/${DEST_NAME}"

    if [ ! -d "${TARGET_DIR}" ]; then
        echo "  SKIP: ${target}/ does not exist"
        continue
    fi

    # Remove stale vendored copy
    if [ -d "${DEST}" ]; then
        echo "  [${target}] Removing stale vendor copy: ${DEST}"
        rm -rf "${DEST}"
    fi

    # Copy source tree (exclude __pycache__, .pyc, tests)
    echo "  [${target}] Copying svn_shared/ → ${DEST}/"
    rsync -a \
        --exclude="__pycache__" \
        --exclude="*.pyc" \
        --exclude="*.pyo" \
        --exclude="tests/" \
        --exclude="*.egg-info/" \
        "${SRC}/" "${DEST}/"

    echo "  [${target}] Done. Vendored: $(find "${DEST}" -name "*.py" | wc -l) Python files."
done

echo ""
echo "=== Vendoring complete ==="
echo ""
echo "Next steps:"
echo "  1. Run: python -m build svn_client  (or svn_server)"
echo "  2. The resulting wheel includes svn_shared/ and needs no PYTHONPATH= at runtime."
echo "  3. Do NOT commit the vendored svn_shared/ copies — add them to .gitignore."
echo ""
echo "To undo vendoring, delete the copied directories:"
for target in ${TARGETS}; do
    echo "    rm -rf ${ROOT_DIR}/${target}/${DEST_NAME}"
done
