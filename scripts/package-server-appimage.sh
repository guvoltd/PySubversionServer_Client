#!/bin/bash
# Build a portable, single-file Linux AppImage for SVN Server Admin.
#
# Unlike the .deb/Flatpak packages, the AppImage bundles its own Python
# interpreter and all dependencies (via PyInstaller), so it runs on any
# reasonably modern x86_64 Linux distro without installing anything.
#
# CAVEAT: privileged actions (create/delete repository, firewall rule,
# systemd service install, etc.) shell out to system-helper.sh via `pkexec`.
# In this portable build the whole bundle -- including that helper script --
# is extracted to a fresh temp directory on every launch, so pkexec/polkit's
# usual path-based trust checks don't line up the way they do for the .deb
# install. Privileged actions may not work from this AppImage; use the .deb
# or Flatpak package if you need those. Everything else (repository
# browsing, hooks editing, non-privileged backups, etc.) works the same.
#
# Prerequisites:
#   The project venv (scripts/ensure-venv.sh) with PyInstaller installed:
#     .venv/bin/python3 -m pip install pyinstaller
#   appimagetool on PATH:
#     https://github.com/AppImage/AppImageKit/releases -> appimagetool-x86_64.AppImage
#     (rename/chmod +x it and place it somewhere on PATH as `appimagetool`)
#
# Usage:
#   scripts/package-server-appimage.sh
#
# Output:
#   svn_server/dist/SVN_Server_Admin-x86_64.AppImage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PKG_DIR="${ROOT_DIR}/svn_server"
DIST_DIR="${PKG_DIR}/dist"
APP_NAME="svn-server-admin"
APP_DISPLAY_NAME="SVN Server Admin"

echo "=== SVN Server Admin — AppImage packaging ==="
echo "  Source : ${PKG_DIR}"
echo "  Output : ${DIST_DIR}"
echo ""
echo "  NOTE: privileged actions (pkexec-based) may not work from this"
echo "        portable build -- see the comment at the top of this script."
echo ""

# Bootstrap the virtual environment
source "${SCRIPT_DIR}/ensure-venv.sh"

if ! "${VENV_PYTHON}" -c "import PyInstaller" &>/dev/null; then
    echo "ERROR: PyInstaller is not installed in the venv." >&2
    echo "       Install: ${VENV_PYTHON} -m pip install pyinstaller" >&2
    exit 1
fi

if ! command -v appimagetool &>/dev/null; then
    echo "ERROR: appimagetool not found on PATH." >&2
    echo "       Download: https://github.com/AppImage/AppImageKit/releases" >&2
    echo "       (grab appimagetool-x86_64.AppImage, chmod +x, put on PATH as 'appimagetool')" >&2
    exit 1
fi

echo "  Building single-file executable with PyInstaller …"
"${VENV_PYTHON}" -m PyInstaller "${PKG_DIR}/pyinstaller/svn-server-admin.spec" --noconfirm \
    --distpath "${PKG_DIR}/pyinstaller/dist" \
    --workpath "${PKG_DIR}/pyinstaller/build"

APPDIR="$(mktemp -d /tmp/svn-server-admin-appdir.XXXXXX)"
trap 'rm -rf "${APPDIR}"' EXIT

echo "  Assembling AppDir at ${APPDIR} …"
mkdir -p "${APPDIR}/usr/bin"
cp "${PKG_DIR}/pyinstaller/dist/${APP_NAME}" "${APPDIR}/usr/bin/${APP_NAME}"
chmod +x "${APPDIR}/usr/bin/${APP_NAME}"

cp "${PKG_DIR}/resources/icons/org.svnsuite.SvnServerAdmin.png" \
   "${APPDIR}/org.svnsuite.SvnServerAdmin.png"

cat > "${APPDIR}/org.svnsuite.SvnServerAdmin.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_DISPLAY_NAME}
Comment=GUI for managing Subversion repositories
Exec=${APP_NAME}
Icon=org.svnsuite.SvnServerAdmin
Terminal=false
Categories=Development;RevisionControl;System;
EOF

cat > "${APPDIR}/AppRun" <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\${0}")")"
exec "\${HERE}/usr/bin/${APP_NAME}" "\$@"
EOF
chmod +x "${APPDIR}/AppRun"

mkdir -p "${DIST_DIR}"
echo "  Running appimagetool …"
ARCH=x86_64 appimagetool "${APPDIR}" "${DIST_DIR}/SVN_Server_Admin-x86_64.AppImage"

echo ""
echo "=== AppImage built successfully ==="
echo "    ${DIST_DIR}/SVN_Server_Admin-x86_64.AppImage"
echo "    Run with: chmod +x ${DIST_DIR}/SVN_Server_Admin-x86_64.AppImage && ${DIST_DIR}/SVN_Server_Admin-x86_64.AppImage"
