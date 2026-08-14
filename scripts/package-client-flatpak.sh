#!/bin/bash
# Build and (optionally) install the SVN Client as a Flatpak.
#
# Environment variables:
#   FLATPAK_INSTALL   set to "1" to install into the user Flatpak store after build
#   FLATPAK_REPO      path to a local Flatpak repository (default: ./flatpak-repo)
#   FLATPAK_BUILD_DIR build directory (default: ./flatpak-build/svn-client)
#
# Prerequisites:
#   flatpak flatpak-builder
#   flatpak install flathub org.kde.Platform//6.8 org.kde.Sdk//6.8
#   flatpak install flathub org.freedesktop.Sdk.Extension.python313//24.08
#   Run flatpak-pip-generator first (see svn_client/flatpak/org.svnsuite.SvnClient.yml)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST="${ROOT_DIR}/svn_client/flatpak/org.svnsuite.SvnClient.yml"
BUILD_DIR="${FLATPAK_BUILD_DIR:-${ROOT_DIR}/flatpak-build/svn-client}"
REPO_DIR="${FLATPAK_REPO:-${ROOT_DIR}/flatpak-repo}"

echo "=== SVN Client — Flatpak packaging ==="
echo "  Manifest : ${MANIFEST}"
echo "  Build dir: ${BUILD_DIR}"
echo "  Repo     : ${REPO_DIR}"
echo ""

# Validate prerequisites
if ! command -v flatpak-builder &>/dev/null; then
    echo "ERROR: flatpak-builder is not installed." >&2
    echo "       Install it with: sudo apt install flatpak-builder" >&2
    exit 1
fi

if ! flatpak info org.kde.Platform//6.8 &>/dev/null; then
    echo "ERROR: Flatpak runtime org.kde.Platform//6.8 is not installed." >&2
    echo "       Run: flatpak install flathub org.kde.Platform//6.8 org.kde.Sdk//6.8" >&2
    exit 1
fi

# Check for the pip-generator output used by the manifest
DEPS_JSON="${ROOT_DIR}/svn_client/flatpak/python-deps.json"
if [ ! -f "${DEPS_JSON}" ]; then
    echo "WARNING: ${DEPS_JSON} not found."
    echo "         Run flatpak-pip-generator to generate it, or use --allow-wget."
    echo "         Attempting build with --allow-wget (requires internet access)…"
    EXTRA_FLAGS="--allow-wget"
else
    EXTRA_FLAGS=""
fi

mkdir -p "${REPO_DIR}"

flatpak-builder \
    --force-clean \
    --repo="${REPO_DIR}" \
    ${EXTRA_FLAGS} \
    "${BUILD_DIR}" \
    "${MANIFEST}"

echo ""
echo "=== Build complete. Bundle written to: ${REPO_DIR} ==="

if [ "${FLATPAK_INSTALL:-0}" = "1" ]; then
    echo "=== Installing into user Flatpak store… ==="
    flatpak --user remote-add --no-gpg-verify --if-not-exists \
        svnsuite-local "${REPO_DIR}" || true
    flatpak --user install --or-update svnsuite-local org.svnsuite.SvnClient
    echo "=== Installation complete. Run: flatpak run org.svnsuite.SvnClient ==="
fi
