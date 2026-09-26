# Installing from the `.whl` / `.tar.gz` build

`scripts/build-all.sh` (or `python -m build svn_client` / `svn_server`
directly) produces two files per app in `svn_client/dist/` and
`svn_server/dist/`:

- `svn_client-0.1.0-py3-none-any.whl` / `svn_server_admin-0.1.0-py3-none-any.whl`
  — the **wheel**, a prebuilt, ready-to-install package. Use this one normally.
- `svn_client-0.1.0.tar.gz` / `svn_server_admin-0.1.0.tar.gz`
  — the **sdist** (source distribution). `pip` can install from it directly
  too (it builds the wheel from it on the fly), or use it if you need to
  inspect/patch the source before installing.

Both are plain, pure-Python wheels (no compiled extensions), so the exact
same `pip install` steps work on Debian, any other Linux distro, and
Windows — there's no distro-specific packaging step needed for this path
(that's what the `.deb`/Flatpak/AppImage/Windows-installer builds are for;
see [`docs/standalone-packaging.md`](standalone-packaging.md) if you want
those instead).

## Prerequisites (all platforms)

- **Python 3.10+**
- **The `svn` command-line client**, installed separately and on `PATH` —
  both apps shell out to it; it is *not* something pip can install.
  - Debian/Ubuntu: `sudo apt install subversion`
  - Fedora: `sudo dnf install subversion`
  - Arch: `sudo pacman -S subversion`
  - Windows: install [Slik-SVN](https://sliksvn.com/download/) or
    TortoiseSVN with its "command line client tools" option checked, and
    make sure it's on `PATH` (`svn --version` should work in a new terminal).
- A desktop session (X11/Wayland on Linux, or just a normal desktop on
  Windows) — both are GUI apps built with PySide6 (Qt).

## Debian / Ubuntu / any other Linux

`pipx` is the recommended way to install a GUI/CLI Python app system-wide
without it interfering with your system Python or other projects:

```bash
sudo apt install pipx      # Debian/Ubuntu; use your distro's package manager elsewhere
pipx ensurepath            # once, then restart your terminal

pipx install svn_client/dist/svn_client-0.1.0-py3-none-any.whl
pipx install svn_server/dist/svn_server_admin-0.1.0-py3-none-any.whl
```

This installs each app into its own isolated environment and puts
`svn-client` / `svn-server-admin` on your `PATH`. Run them from a terminal,
or find them in your desktop's application menu once you've installed the
`.desktop` files too (optional, see note below).

**Without `pipx`** — a plain venv works just as well if you don't want
`pipx`:

```bash
python3 -m venv ~/.local/share/svnsuite-venv
~/.local/share/svnsuite-venv/bin/pip install \
    svn_client/dist/svn_client-0.1.0-py3-none-any.whl \
    svn_server/dist/svn_server_admin-0.1.0-py3-none-any.whl

# Run:
~/.local/share/svnsuite-venv/bin/svn-client
~/.local/share/svnsuite-venv/bin/svn-server-admin

# Optional: put them on PATH
ln -s ~/.local/share/svnsuite-venv/bin/svn-client ~/.local/bin/svn-client
ln -s ~/.local/share/svnsuite-venv/bin/svn-server-admin ~/.local/bin/svn-server-admin
```

**Desktop menu entry (optional):** `pip`/`pipx` only installs the Python
package and the `svn-client`/`svn-server-admin` commands — it does not
register a desktop menu entry or icon (that's what the `.deb` package does).
To get one anyway, copy the existing `.desktop` file and point it at your
installed command:

```bash
cp svn_client/resources/org.svnsuite.SvnClient.desktop ~/.local/share/applications/
# edit the Exec= line if svn-client isn't on PATH, e.g.:
#   Exec=/home/you/.local/bin/svn-client %F
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
```

(Same idea for the server admin app's `.desktop` file in `svn_server/resources/`.)

## Windows

```powershell
py -m venv $env:USERPROFILE\svnsuite-venv
& "$env:USERPROFILE\svnsuite-venv\Scripts\pip.exe" install `
    svn_client\dist\svn_client-0.1.0-py3-none-any.whl `
    svn_server\dist\svn_server_admin-0.1.0-py3-none-any.whl

# Run:
& "$env:USERPROFILE\svnsuite-venv\Scripts\svn-client.exe"
& "$env:USERPROFILE\svnsuite-venv\Scripts\svn-server-admin.exe"
```

If you'd rather have a double-clickable Start Menu shortcut instead of
running from a venv each time, use the single-file `.exe` + Inno Setup
installer path instead — see
[`docs/standalone-packaging.md`](standalone-packaging.md).

## Uninstalling

```bash
pipx uninstall svn-client
pipx uninstall svn-server-admin
# or, if you used a plain venv, just delete the venv directory
```

## Note on Server Admin's privileged actions

Repository actions that need root (creating a repository under a
root-owned path, adding a firewall rule, installing a systemd unit, etc.)
call `pkexec` on a bundled helper script. That still works from a
pip/pipx install (the script is bundled in the wheel at a real, stable
installed path — unlike the portable AppImage/exe build, where it isn't;
see the caveat in `docs/standalone-packaging.md`). You'll still need
`pkexec`/polkit available on your system, which is standard on most
desktop Linux distros.

## If you already have older copies of these two files

An earlier version of `svn_client/pyproject.toml` and
`svn_server/pyproject.toml` had a packaging bug: the package-discovery
config didn't match this repo's actual directory layout, so
`python -m build` silently produced a `.whl`/`.tar.gz` containing **only
metadata — no actual application code**. Installing one of those would
succeed, but running `svn-client`/`svn-server-admin` would immediately fail
with `ModuleNotFoundError`. That's now fixed (see `svn_client/pyproject.toml`
/ `svn_server/pyproject.toml`, and `scripts/vendor-shared.sh` is now wired
into `scripts/build-all.sh`). If your two files predate this fix, rebuild
them first:

```bash
scripts/build-all.sh
```

and use the freshly generated `svn_client/dist/*.whl` / `svn_server/dist/*.whl`.
