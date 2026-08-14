# SVN Client

A Linux desktop GUI for Subversion working copy operations. This application provides a graphical interface for the everyday `svn` commands that developers use — checkout, status, diff, commit, log, branch, and conflict resolution.

## Features

### Working Copy Management
- **Open** an existing working copy from the filesystem.
- **Checkout** a remote repository to a local path (supports `svn://`, `http://`, `https://`, `file://` URLs).
- **Display** working copy info — URL, revision, UUID, repository root.

### Status & Diff
- **File status tree** with icons for modified (M), added (A), deleted (D), conflicted (C), and unversioned (?) files.
- **Inline diff viewer** with syntax highlighting — side-by-side and unified modes.
- **Diff against** BASE, HEAD, or any arbitrary revision.

### Log & History
- **Revision log** with author, date, message, and changed paths.
- **Filter/search** by author, date range, path, or message text.
- **Show diff** for any log entry with a double-click.

### Core Operations
- **Update** working copy with progress feedback.
- **Commit** with multi-line message editor and per-file selection.
- **Add / Remove** files from version control.
- **Revert** changes at file or directory level.

### Branching & Tagging
- **Switch** working copy to a different branch or tag.
- **Create** branches and tags via server-side copy.
- **Visual branch selector** with standard layout detection (trunk/branches/tags).

### Conflict Resolution
- **Detect and list** conflicted files with conflict type.
- **Three-way merge guidance** — mine / theirs / base with visual indicators.
- **Mark resolved** after manual editing.

### General
- **Credential handling** via OS keyring (GNOME Keyring / KDE Wallet) — no plaintext passwords.
- **Light and dark themes** with auto-detection of system preference.
- **Keyboard shortcuts** for all primary operations.
- **Window geometry persistence** between sessions.

## Prerequisites

- **Python 3.10+**
- **Subversion 1.10+** CLI tools: `svn` (required), `svnadmin` (optional, for local repos)
- **Linux** desktop environment (X11 or Wayland)

## Installation

### Quick Run (recommended — uses virtual environment)

From the workspace root, every `make` target auto-creates a `.venv/` and installs dependencies:

```bash
make run-client    # Creates .venv on first run, then launches the GUI
```

### Development Install (editable mode inside .venv)

```bash
# From workspace root — installs with dev dependencies into .venv
make dev-client

# Or manually (after make venv)
.venv/bin/pip install -e svn_client[dev]
```

### Production Install (from wheel)

```bash
# Build the wheel first (from workspace root)
make build-client

# Install the wheel into any Python environment
pip install svn_client/dist/svn_client-0.1.0-py3-none-any.whl
```

### Dependencies

**Runtime:**

| Package | Version | Purpose |
|---|---|---|
| `PySide6` | >= 6.7 | Qt 6 GUI framework |
| `keyring` | >= 25.0 | OS-native credential storage |

**Development (optional):**

| Package | Version | Purpose |
|---|---|---|
| `pytest` | >= 8.0 | Test runner |
| `pytest-qt` | >= 4.4 | Qt widget testing |
| `pytest-cov` | >= 5.0 | Coverage reporting |
| `ruff` | >= 0.4 | Linter and formatter |
| `mypy` | >= 1.10 | Static type checker |

## Running

### After Installation

```bash
# Via console script (available after make dev-client)
svn-client

# Via Python module (using the venv)
.venv/bin/python -m svn_client
```

### Development Mode (without editable install)

```bash
# From workspace root — auto-creates .venv if needed
./scripts/run-dev.sh client

# Or via make
make run-client

# Or manually
PYTHONPATH=. .venv/bin/python -m svn_client
```

### First Launch

1. The application opens with an empty file tree and a welcome message.
2. Go to **File → Open Working Copy** (or press `Ctrl+O`) and select a directory that is an SVN working copy.
3. The file tree populates with status icons showing modified, added, deleted, and unversioned files.
4. Use the toolbar or SVN menu to update, commit, view log, diff, or branch.

To checkout a new repository:
1. Go to **File → Checkout** (or press `Ctrl+Shift+O`).
2. Enter the repository URL and a local destination path.
3. The checkout runs with progress feedback in the status bar.

## Project Structure

```
svn_client/
├── __init__.py          # Package init, version string
├── __main__.py          # Entry point (svn-client command)
├── app.py               # ClientMainWindow — main window, menus, toolbar, layout
├── pyproject.toml       # PEP 621 project metadata and build config
├── resources/
│   └── icons/           # Application icons (placeholder)
├── tests/
│   └── __init__.py      # Client UI tests (to be expanded)
└── README.md            # This file
```

**Planned modules** (Phase 3 — not yet implemented):

| Module | Purpose |
|---|---|
| `status_tree.py` | QTreeView with status icons, context menu, checkbox selection |
| `diff_viewer.py` | Side-by-side and unified diff with syntax highlighting |
| `log_viewer.py` | Revision log table with detail panel and search/filter |
| `checkout_dialog.py` | Checkout wizard with URL validation and progress |
| `commit_dialog.py` | Commit dialog with file selector and message editor |
| `branch_dialog.py` | Branch/tag creation and switch dialog |
| `conflict_panel.py` | Conflict list with resolution guidance |

## Testing

```bash
# Run client tests only (uses .venv automatically)
make test-client

# Run all tests (shared + client + server)
make test-all

# Run with verbose output
PYTHONPATH=. .venv/bin/python -m pytest svn_client/tests/ -v
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open working copy |
| `Ctrl+Shift+O` | Checkout repository |
| `Ctrl+Q` | Quit |
| `F5` | Refresh |

More shortcuts will be added as UI widgets are implemented.

## Configuration

Settings are stored via `QSettings` at `~/.config/svn-client/settings.ini`:

```ini
[General]
theme=auto              # "light", "dark", or "auto"
last_wc_path=/home/user/project

[Client]
diff_mode=side-by-side  # "side-by-side" or "unified"
log_limit=500
show_unversioned=true
```

## Shared Library

This application depends on `svn_shared/` for all SVN operations, credential management, and shared widgets. At build time, `svn_shared/` is vendored into the package — there is no separate shared library to install.

## License

LGPL-3.0-or-later
