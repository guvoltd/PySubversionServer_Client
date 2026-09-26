# PyInstaller spec for SVN Client -- single-file executable.
#
# Build (from repo root, with the project venv active and PyInstaller installed):
#   pyinstaller svn_client/pyinstaller/svn-client.spec --noconfirm
#
# Output: svn_client/pyinstaller/dist/svn-client(.exe)
#
# Notes:
#   - `datas` mirrors the source-tree-relative paths the app looks up at
#     runtime via os.path.dirname(__file__) (see svn_client/app.py's
#     _load_theme and svn_client/__main__.py's icon lookup), so those lookups
#     keep working unchanged inside the frozen bundle.
#   - `icon=` only affects the Windows/macOS executable's own file icon; the
#     window/taskbar icon is set at runtime via app.setWindowIcon() using the
#     bundled .ico (see svn_client/__main__.py).

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
        (os.path.join(ROOT_DIR, "svn_client", "resources", "icons"),
         os.path.join("svn_client", "resources", "icons")),
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
    name="svn-client",
    icon=os.path.join(ROOT_DIR, "svn_client", "resources", "icons", "org.svnsuite.SvnClient.ico"),
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
