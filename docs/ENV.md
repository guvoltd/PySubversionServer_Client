# Environment Variables — SVN Desktop Suite

This document lists all environment variables recognised by the SVN Desktop Suite
build system, packaging scripts, and applications at runtime.

---

## Build & Venv

| Variable | Default | Description |
|---|---|---|
| `PYTHONPATH` | *(empty)* | Set to `.` when running from the workspace root so both `svn_client` and `svn_server` can resolve `svn_shared` as a sibling package. The Makefile sets this automatically. |
| `VENV_DIR` | `.venv/` | Virtual environment directory used by `ensure-venv.sh` and the Makefile. Override to use a shared venv across projects. |

---

## Flatpak Packaging (`scripts/package-*-flatpak.sh`)

| Variable | Default | Description |
|---|---|---|
| `FLATPAK_INSTALL` | `0` | Set to `1` to install the built Flatpak into the user store after building. |
| `FLATPAK_REPO` | `./flatpak-repo` | Path to the local Flatpak repository where the built bundle is exported. |
| `FLATPAK_BUILD_DIR` | `./flatpak-build/<app>` | Temporary directory used by `flatpak-builder` for the build tree. |

---

## Debian Packaging (`scripts/package-*-deb.sh`)

| Variable | Default | Description |
|---|---|---|
| `DEB_BUILD_OPTIONS` | *(empty)* | Standard `dpkg-buildpackage` options, e.g. `nocheck` to skip test suite during `.deb` build. |
| `SIGN_KEY` | *(empty)* | GPG key ID to sign the resulting `.deb`. If unset the package is built unsigned (`-us -uc`). |

---

## Vendoring (`scripts/vendor-shared.sh`)

| Variable | Default | Description |
|---|---|---|
| `VENDOR_TARGETS` | `svn_client svn_server` | Space-separated list of app package directories into which `svn_shared/` is copied. |
| `VENDOR_DEST_NAME` | `svn_shared` | Destination subdirectory name within each app package. Override if you rename the shared package. |

---

## Runtime (both applications)

| Variable | Default | Description |
|---|---|---|
| `XDG_DATA_HOME` | `~/.local/share` | Controls where application logs and data are stored. Crash logs are written to `$XDG_DATA_HOME/<app-name>/logs/`. |
| `XDG_CONFIG_HOME` | `~/.config` | Used by Qt / QSettings for `svnsuite/svn-client.ini` and `svnsuite/svn-server-admin.ini`. |
| `SVN_SSH` | *(system default)* | SSH command used by `svn+ssh://` URLs. Set to configure a specific key: `SVN_SSH="ssh -i ~/.ssh/svn_key"`. |
| `EDITOR` | `xdg-open` | Editor launched by the Conflict Panel's "Edit Manually" action when `$EDITOR` is set. Falls back to `xdg-open`. |

---

## Development Helpers

```bash
# Run client from workspace root (PYTHONPATH needed so svn_shared is importable)
PYTHONPATH=. .venv/bin/python -m svn_client

# Run server admin
PYTHONPATH=. .venv/bin/python -m svn_server

# Run all tests with coverage
PYTHONPATH=. .venv/bin/python -m pytest svn_shared/tests/ --cov=svn_shared

# Build Flatpak and immediately install it
FLATPAK_INSTALL=1 bash scripts/package-client-flatpak.sh

# Build .deb signed with a specific GPG key
SIGN_KEY=ABCD1234 bash scripts/package-client-deb.sh

# Vendor svn_shared into both apps before building standalone wheels
bash scripts/vendor-shared.sh
```
