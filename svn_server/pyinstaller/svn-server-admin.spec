# PyInstaller spec for SVN Server Admin -- single-file executable.
#
# Build (from repo root, with the project venv active and PyInstaller installed):
#   pyinstaller svn_server/pyinstaller/svn-server-admin.spec --noconfirm
#
# Output: svn_server/pyinstaller/dist/svn-server-admin(.exe)
#
# IMPORTANT CAVEAT -- privileged actions (create/delete repository, firewall
# rule, systemd service install, etc.) shell out to
# svn_server/resources/system-helper.sh via `pkexec`. In a --onefile build,
# the whole bundle (including this script) is extracted to a fresh temporary
# directory on every launch, and pkexec/polkit policies generally expect a
# stable, installed path. Those privileged actions may not work from this
# portable build the way they do from the .deb install; the Debian/Flatpak
# packages remain the supported path for privileged server administration.
# Everything else (repository browsing, hooks editing, backups you can run as
# your own user, etc.) works the same as from source.

import os

block_cipher = None

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT_DIR = os.path.abspath(os.path.join(SPEC_DIR, "..", ".."))

a = Analysis(
    [os.path.join(SPEC_DIR, "launcher.py")],
    pathex=[ROOT_DIR],
    binaries=[],
    datas=[
        (os.path.join(ROOT_DIR, "svn_shared", "resources", "styles"),
         os.path.join("svn_shared", "resources", "styles")),
        (os.path.join(ROOT_DIR, "svn_server", "resources", "icons"),
         os.path.join("svn_server", "resources", "icons")),
        (os.path.join(ROOT_DIR, "svn_server", "resources", "system-helper.sh"),
         os.path.join("svn_server", "resources")),
    ],
    hiddenimports=[
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
        "keyring.backends.Windows",
        "keyring.backends.macOS",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="svn-server-admin",
    icon=os.path.join(
        ROOT_DIR, "svn_server", "resources", "icons", "org.svnsuite.SvnServerAdmin.ico"
    ),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
