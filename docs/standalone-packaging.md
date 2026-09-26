# Standalone executables & installers

In addition to the Flatpak and `.deb` packages (which require the target
machine to have Python, PySide6, etc. available or install them as
dependencies), both apps can be built as **single-file executables** that
bundle their own Python interpreter and all dependencies, using
[PyInstaller](https://pyinstaller.org/). Those executables are then wrapped
into a proper installer per platform:

| Platform | Single-file executable | Installer |
|---|---|---|
| Linux | PyInstaller `--onefile` binary | [AppImage](https://appimage.org/) (portable, no install step at all) |
| Windows | PyInstaller `--onefile` `.exe` | [Inno Setup](https://jrsoftware.org/isinfo.php) `.exe` installer (Start Menu shortcut, uninstaller) |

## Layout

```
svn_client/pyinstaller/svn-client.spec        PyInstaller build spec
svn_client/windows/svn-client.iss             Inno Setup installer script
svn_server/pyinstaller/svn-server-admin.spec
svn_server/windows/svn-server-admin.iss
svn_client/resources/icons/*.ico, *.png       Generated from the existing .svg icon
svn_server/resources/icons/*.ico, *.png
```

The `.spec` files are cross-platform — the same file is used to build on
both Linux and Windows; only the packaging step after it (AppImage vs. Inno
Setup) differs.

## Linux: AppImage

```bash
# one-time: install appimagetool and put it on PATH as `appimagetool`
# https://github.com/AppImage/AppImageKit/releases -> appimagetool-x86_64.AppImage

scripts/package-client-appimage.sh
scripts/package-server-appimage.sh
```

Output: `svn_client/dist/SVN_Client-x86_64.AppImage`,
`svn_server/dist/SVN_Server_Admin-x86_64.AppImage`. Each is a single
executable file — `chmod +x` and run it, no installation needed.

## Windows: .exe + installer

Run **on a Windows machine** (PyInstaller doesn't cross-compile — a Windows
build has to happen on Windows, same as a macOS build would have to happen
on macOS):

```powershell
# one-time: install Inno Setup 6 (https://jrsoftware.org/isinfo.php)
# and make sure ISCC.exe is on PATH

.\scripts\package-client-windows.ps1
.\scripts\package-server-windows.ps1
```

Each script builds the `.exe` with PyInstaller, then compiles the
corresponding `.iss` script into an installer under `svn_*\windows\Output\`.

## What's bundled

Both specs bundle `svn_shared/resources/styles/*.qss` (the light/dark/blue
themes) so theme switching works identically in the packaged build. The
server spec additionally bundles `svn_server/resources/system-helper.sh`
(see caveat below). Window/taskbar icons are set at runtime from the bundled
`.ico` files (`svn_client/__main__.py`, `svn_server/__main__.py`).

## Caveat: Server Admin privileged actions

Server Admin shells out to `system-helper.sh` via `pkexec` for privileged
actions (creating/deleting a repository under a root-owned path, adding a
firewall rule, installing a systemd unit, etc.). In a `--onefile` build, the
whole bundle — including that helper script — is extracted to a **fresh
temporary directory on every launch**. `pkexec`/polkit's usual trust model
expects a stable, installed path, so those specific actions may not behave
the same way from a portable AppImage/exe as they do from the `.deb`
install. Everything else (browsing repositories, editing hooks, backups you
can run as your own user, etc.) works the same regardless of how the app
was packaged. If you rely on the privileged actions, use the `.deb` or
Flatpak package.

On Windows there's no `pkexec` equivalent wired up at all yet; running the
app elevated is the closest analog for now.

## Regenerating the icons

The `.ico`/`.png` files are rasterized from the existing `.svg` icons. If
the source `.svg` changes, regenerate with:

```bash
.venv/bin/python3 -m pip install pillow  # if not already installed
.venv/bin/python3 - <<'EOF'
import sys
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from PIL import Image

app = QApplication(sys.argv)

def render_png(svg_path, out_path, size):
    r = QSvgRenderer(svg_path)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    r.render(p)
    p.end()
    img.save(out_path, "PNG")

for svg, base in [
    ("svn_client/resources/icons/org.svnsuite.SvnClient.svg",
     "svn_client/resources/icons/org.svnsuite.SvnClient"),
    ("svn_server/resources/icons/org.svnsuite.SvnServerAdmin.svg",
     "svn_server/resources/icons/org.svnsuite.SvnServerAdmin"),
]:
    render_png(svg, base + ".png", 256)
    Image.open(base + ".png").convert("RGBA").save(
        base + ".ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
    )
EOF
```
