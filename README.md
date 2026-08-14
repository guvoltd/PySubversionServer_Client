# SVN Desktop Suite

A Linux-first desktop application suite for Subversion, consisting of two independent GUI tools developed in a single workspace:

- **SVN Client** (`svn_client/`) — developer-facing GUI for working copy operations (checkout, commit, diff, log, branch, conflict resolution).
- **SVN Server Admin** (`svn_server/`) — admin-facing GUI for repository management (create/delete repos, access control, hooks, backup/restore).

Both applications share a common service library (`svn_shared/`) that is vendored into each package at build time. They are built, packaged, and distributed as **separate installable packages** — install one or both depending on your role.

## Tech Stack

| Component | Choice |
|---|---|
| GUI Framework | PySide6 (Qt 6 for Python) — LGPL v3 |
| Language | Python 3.10+ |
| SVN Integration | subprocess wrapping `svn` / `svnadmin` / `svnlook` CLI |
| Credential Storage | `keyring` library (GNOME Keyring / KDE Wallet via Secret Service API) |
| Packaging | Flatpak (primary) + .deb (secondary) |
| Testing | pytest + pytest-qt |
| Linting | ruff + mypy |

## Prerequisites

- **Python 3.10+** with pip
- **Subversion 1.10+** CLI tools (`svn`, `svnadmin`, `svnlook`)
- **Linux** desktop environment with X11 or Wayland

Verify your setup:

```bash
python3 --version    # 3.10 or higher
svn --version        # 1.10 or higher
```

## Workspace Structure

```
.
├── svn_client/          # SVN Client application (separate package)
├── svn_server/          # SVN Server Admin application (separate package)
├── svn_shared/          # Shared service library (vendored into both apps)
├── scripts/             # Build, package, and dev-run helper scripts
├── docs/kiro/           # Multi-agent documentation system
├── Makefile             # Top-level orchestrator (see commands below)
└── README.md            # This file
```

## Quick Start

Every `make` target automatically creates a `.venv/` virtual environment on first run and installs all dependencies into it. You never install packages into your system Python.

```bash
# Run the SVN Client (creates .venv on first run, then launches)
make run-client

# Run the SVN Server Admin
make run-server

# Run all tests
make test-all
```

Or use the shell script directly (also auto-creates the venv):

```bash
./scripts/run-dev.sh client    # Launch SVN Client
./scripts/run-dev.sh server    # Launch SVN Server Admin
```

To install in editable mode inside the venv (for development with console scripts):

```bash
make dev-client    # pip install -e svn_client[dev] inside .venv
make dev-server    # pip install -e svn_server[dev] inside .venv
make dev-all       # Both
```

## Makefile Commands Reference

Run `make help` to see all available targets. Below is the full reference.

All targets depend on the `venv` target — the virtual environment at `.venv/` is created automatically on first use and reused on subsequent runs.

### Virtual Environment

| Command | Description |
|---|---|
| `make venv` | Create the `.venv/` virtual environment and install all dependencies (PySide6, keyring, pytest, ruff, mypy, build). Runs automatically as a prerequisite of every other target. If `.venv/` already exists, this is a no-op. |
| `make clean-venv` | Remove `.venv/` entirely plus all build artifacts. Run `make venv` to recreate from scratch. |

### Development Install

| Command | Description |
|---|---|
| `make dev-client` | Install SVN Client in editable mode inside `.venv/` with dev dependencies (`pip install -e svn_client[dev]`). Source changes take effect immediately. |
| `make dev-server` | Install SVN Server Admin in editable mode inside `.venv/`. |
| `make dev-all` | Install both applications in editable mode. |

### Run

| Command | Description |
|---|---|
| `make run-client` | Launch the SVN Client GUI using `.venv/bin/python`. Creates the venv first if needed. |
| `make run-server` | Launch the SVN Server Admin GUI using `.venv/bin/python`. |

### Build

| Command | Description |
|---|---|
| `make build-client` | Build the SVN Client wheel (`.whl`) and source distribution into `svn_client/dist/`. Uses `.venv/bin/python -m build`. |
| `make build-server` | Build the SVN Server Admin wheel and source distribution into `svn_server/dist/`. |
| `make build-all` | Build both wheels sequentially. |

### Testing

| Command | Description |
|---|---|
| `make test-shared` | Run unit tests for the shared library only (`svn_shared/tests/`). These tests mock subprocess calls and do not require SVN CLI or a display server. Fast — runs in ~1 second. |
| `make test-client` | Run tests for the SVN Client (`svn_client/tests/`). Includes UI smoke tests that may require a display server or `xvfb-run`. |
| `make test-server` | Run tests for the SVN Server Admin (`svn_server/tests/`). |
| `make test-all` | Run all tests across all three packages in a single pytest session. This is the command CI should use. |
| `make coverage` | Run shared library tests with coverage reporting. Generates an HTML report in `htmlcov/` and prints a summary to the terminal. Target: 80% line coverage on `svn_shared/`. |

### Linting & Type Checking

| Command | Description |
|---|---|
| `make lint-all` | Run `ruff check` across all three packages (`svn_shared/`, `svn_client/`, `svn_server/`). Checks for style issues, import ordering, and common errors. Config: `line-length = 100`, rules `E, F, I, W, UP`. |
| `make typecheck` | Run `mypy` across all three packages. Checks type annotations for correctness. Strict mode is enabled on the shared service layer. |

### Packaging & Distribution

| Command | Description |
|---|---|
| `make package-all` | Build all distribution packages (Flatpak + .deb) for both applications. Calls the scripts in `scripts/` sequentially. Currently outputs placeholder messages — packaging manifests are defined but not yet fully implemented. |

The individual packaging scripts are:

| Script | Description |
|---|---|
| `scripts/package-client-flatpak.sh` | Build SVN Client Flatpak bundle |
| `scripts/package-client-deb.sh` | Build SVN Client .deb package |
| `scripts/package-server-flatpak.sh` | Build SVN Server Admin Flatpak bundle |
| `scripts/package-server-deb.sh` | Build SVN Server Admin .deb package |
| `scripts/build-all.sh` | Build both wheels (shell wrapper for CI) |
| `scripts/run-dev.sh` | Launch either app in dev mode: `./scripts/run-dev.sh client` or `server` |

### Cleanup

| Command | Description |
|---|---|
| `make clean` | Remove all build artifacts: `dist/`, `build/`, `*.egg-info` directories from both projects, plus `.pytest_cache`, `.mypy_cache`, `htmlcov`, `.kiro_tmp`, and all `__pycache__` directories. **Keeps `.venv/` intact.** |
| `make clean-venv` | Remove everything `clean` removes **plus** the `.venv/` directory. Use this for a full reset. Run `make venv` afterwards to recreate. |

### Overriding Python

The Makefile uses the system `python3` only to create the venv. All other operations use `.venv/bin/python`. To use a specific Python version for the venv:

```bash
# Remove existing venv and recreate with a specific Python
make clean-venv
python3.12 -m venv .venv
make venv   # installs dependencies into the new venv
```

## Documentation

The `docs/kiro/` directory contains the multi-agent documentation system:

| File | Purpose |
|---|---|
| `docs/kiro/kiro.md` | Project hub — status, decisions, architecture, session handoff |
| `docs/kiro/requirements.md` | Product requirements and technology decisions |
| `docs/kiro/design.md` | Architecture, module decomposition, wireframes |
| `docs/kiro/code_tasks.md` | Implementation task breakdown with status tracking |
| `docs/kiro/testing_steps.md` | Test plan, cases, fixtures, CI pipeline |
| `docs/kiro/aiAgents/` | Agent role definitions (requirements, design, code, test) |

## License

LGPL-3.0-or-later
