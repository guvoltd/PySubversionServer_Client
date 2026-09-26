#!/bin/bash
# Build a portable, single-file Linux AppImage for SVN Client.
#
# Unlike the .deb/Flatpak packages, the AppImage bundles its own Python
# interpreter and all dependencies (via PyInstaller), so it runs on any
# reasonably modern x86_64 Linux distro without installing anything.
#
# Prerequisites:
#   The project venv (scripts/ensure-venv.sh) with PyInstaller installed:
#     .venv/bin/python3 -m pip install pyinstaller
#   appimagetool on PATH:
#     https://github.com/AppImage/AppImageKit/releases -> appimagetool-x86_64.AppImage
#     (rename/chmod +x it and place it somewhere on PATH as `appimagetool`)
#
# Usage:
#   scripts/package-client-appimage.sh
#
# Output:
#   svn_client/dist/SVN_Client-x86_64.AppImage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PKG_DIR="${ROOT_DIR}/svn_client"
DIST_DIR="${PKG_DIR}/dist"
APP_NAME="svn-client"
APP_DISPLAY_NAME="SVN Client"

echo "=== SVN Client — AppImage packaging ==="
echo "  Source : ${PKG_DIR}"
echo "  Output : ${DIST_DIR}"
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
"${VENV_PYTHON}" -m PyInstaller "${PKG_DIR}/pyinstaller/svn-client.spec" --noconfirm \
    --distpath "${PKG_DIR}/pyinstaller/dist" \
    --workpath "${PKG_DIR}/pyinstaller/build"

APPDIR="$(mktemp -d /tmp/svn-client-appdir.XXXXXX)"
trap 'rm -rf "${APPDIR}"' EXIT

echo "  Assembling AppDir at ${APPDIR} …"
mkdir -p "${APPDIR}/usr/bin"
cp "${PKG_DIR}/pyinstaller/dist/${APP_NAME}" "${APPDIR}/usr/bin/${APP_NAME}"
chmod +x "${APPDIR}/usr/bin/${APP_NAME}"

cp "${PKG_DIR}/resources/icons/org.svnsuite.SvnClient.png" \
   "${APPDIR}/org.svnsuite.SvnClient.png"

cat > "${APPDIR}/org.svnsuite.SvnClient.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_DISPLAY_NAME}
Comment=GUI for Subversion working copy operations
Exec=${APP_NAME} %F
Icon=org.svnsuite.SvnClient
Terminal=false
Categories=Development;RevisionControl;
MimeType=inode/directory;
EOF

cat > "${APPDIR}/AppRun" <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\${0}")")"
exec "\${HERE}/usr/bin/${APP_NAME}" "\$@"
EOF
chmod +x "${APPDIR}/AppRun"

mkdir -p "${DIST_DIR}"
echo "  Running appimagetool …"
ARCH=x86_64 appimagetool "${APPDIR}" "${DIST_DIR}/SVN_Client-x86_64.AppImage"

echo ""
echo "=== AppImage built successfully ==="
echo "    ${DIST_DIR}/SVN_Client-x86_64.AppImage"
echo "    Run with: chmod +x ${DIST_DIR}/SVN_Client-x86_64.AppImage && ${DIST_DIR}/SVN_Client-x86_64.AppImage"
