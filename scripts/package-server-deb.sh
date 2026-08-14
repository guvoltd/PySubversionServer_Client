#!/bin/bash
# Build a Debian .deb package for SVN Server Admin.
#
# The source is copied to /tmp before building because dpkg-deb requires Unix
# permission bits that NTFS and some other filesystems cannot provide.
# The resulting .deb is placed in svn_server/dist/.
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
#   scripts/package-server-deb.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PKG_DIR="${ROOT_DIR}/svn_server"
DIST_DIR="${PKG_DIR}/dist"

echo "=== SVN Server Admin — Debian packaging ==="
echo "  Source      : ${PKG_DIR}"
echo "  Output      : ${DIST_DIR}"
echo ""

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

BUILD_TMP="$(mktemp -d /tmp/svn-server-admin-deb.XXXXXX)"
trap 'rm -rf "${BUILD_TMP}"' EXIT

echo "  Copying source to ${BUILD_TMP}/ …"
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='dist/' \
    "${PKG_DIR}/" "${BUILD_TMP}/"

rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' \
    "${ROOT_DIR}/svn_shared/" "${BUILD_TMP}/svn_shared/"

# Fix permissions (NTFS reports all dirs as 777, which dpkg-deb rejects)
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

echo ""
for f in /tmp/svn-server-admin_*.deb /tmp/svn-server-admin_*.changes /tmp/svn-server-admin_*.buildinfo; do
    [ -f "${f}" ] && mv "${f}" "${DIST_DIR}/" && echo "  → ${DIST_DIR}/$(basename "${f}")"
done

echo ""
echo "=== .deb built successfully ==="
echo "    Install with: sudo dpkg -i ${DIST_DIR}/svn-server-admin_*.deb"
