#!/bin/bash
# Build a Debian .deb package for SVN Client.
#
# The source is copied to /tmp before building because dpkg-deb requires Unix
# permission bits that NTFS and some other filesystems cannot provide.
# The resulting .deb is placed in svn_client/dist/.
#
# Environment variables:
#   DEB_BUILD_OPTIONS   passed to dpkg-buildpackage (e.g. "nocheck" to skip tests)
#   SIGN_KEY            GPG key ID to sign the package (leave unset for unsigned build)
#
# Prerequisites:
#   sudo apt install devscripts debhelper dh-python pybuild-plugin-pyproject \
#                    python3-setuptools python3-all
#
# Usage:
#   scripts/package-client-deb.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PKG_DIR="${ROOT_DIR}/svn_client"
DIST_DIR="${PKG_DIR}/dist"

echo "=== SVN Client — Debian packaging ==="
echo "  Source      : ${PKG_DIR}"
echo "  Output      : ${DIST_DIR}"
echo ""

# Prerequisites check
if ! command -v dpkg-buildpackage &>/dev/null; then
    echo "ERROR: dpkg-buildpackage not found." >&2
    echo "       Install: sudo apt install devscripts debhelper dh-python pybuild-plugin-pyproject" >&2
    exit 1
fi

if ! dpkg -l debhelper &>/dev/null; then
    echo "ERROR: debhelper is not installed." >&2
    echo "       Install: sudo apt install debhelper dh-python pybuild-plugin-pyproject" >&2
    exit 1
fi

# Copy source to a native Linux tmpfs so dpkg-deb gets proper Unix permissions.
# NTFS mounts report all dirs as 777, which dpkg-deb rejects (needs 755–775).
BUILD_TMP="$(mktemp -d /tmp/svn-client-deb.XXXXXX)"
trap 'rm -rf "${BUILD_TMP}"' EXIT

echo "  Copying source to ${BUILD_TMP}/ …"
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='dist/' \
    "${PKG_DIR}/" "${BUILD_TMP}/"

# Also copy svn_shared (needed by pybuild)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' \
    "${ROOT_DIR}/svn_shared/" "${BUILD_TMP}/svn_shared/"

# Fix permissions so dpkg-deb is happy (essential when coming from NTFS)
find "${BUILD_TMP}" -type d -exec chmod 755 {} +
find "${BUILD_TMP}" -type f -exec chmod 644 {} +
chmod 755 "${BUILD_TMP}/debian/rules"

mkdir -p "${DIST_DIR}"

if [ -n "${SIGN_KEY:-}" ]; then
    SIGN_FLAGS="-k${SIGN_KEY}"
else
    SIGN_FLAGS="-us -uc"
fi

echo "  Running dpkg-buildpackage …"
cd "${BUILD_TMP}"
dpkg-buildpackage ${SIGN_FLAGS} --build=binary -b

# Move resulting files from the tmp parent directory back to dist/
echo ""
for f in /tmp/svn-client_*.deb /tmp/svn-client_*.changes /tmp/svn-client_*.buildinfo; do
    [ -f "${f}" ] && mv "${f}" "${DIST_DIR}/" && echo "  → ${DIST_DIR}/$(basename "${f}")"
done

echo ""
echo "=== .deb built successfully ==="
echo "    Install with: sudo dpkg -i ${DIST_DIR}/svn-client_*.deb"
