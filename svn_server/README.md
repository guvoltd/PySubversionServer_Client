# SVN Server Admin

A Linux desktop GUI for Subversion repository management. This application provides a graphical interface for tasks that typically require the `svnadmin`, `svnlook`, and `svnserve` command-line tools.

## Features

### Repository Management
- **Create** new repositories with selectable backend (FSFS / FSX) and optional standard layout (trunk/branches/tags).
- **List** all repositories under a configured root directory with metadata (UUID, HEAD revision, size).
- **Delete** repositories with optional automatic backup before removal.
- **Verify** repository integrity.

### User & Access Control
- **Edit `svnserve.conf`** settings via a form UI (anonymous access, authenticated access, realm, password-db, authz-db).
- **Centralized users and groups**: one shared password database and group roster (default
  `/etc/svn/passwd` and `/etc/svn/authz`) used across every repository, managed from dedicated
  Users/Groups tabs in the repository list panel.
- **Suspend / reactivate users** without deleting their account; suspending a user updates the
  central database and every repository's local copy in one confirmation.
- **Per-repository `authz` permissions** with a visual path-based permission matrix (read, read-write, deny per user/group per path), plus a one-click **Fix Permissions** action if a repository's ownership drifts.
- **Guidance panel** for `svnserve` configuration.

### Privileged System Operations
- Repository creation/deletion, service start/stop/restart, and all writes to `/etc/svn/passwd`,
  `/etc/svn/authz`, and `/etc/systemd/system/svnserve.service` are performed by a small root-run
  helper script, authorized per-action via **PolicyKit** (`pkexec`) — the application itself never
  runs as root.
- **Guided first-run setup**: on launch, offers to create the `svnserver` group and `svn` system
  user if missing, add the current desktop user to that group, and open the SVN port (3690/tcp) in
  the firewall if `ufw` is present.
- See [Privileged Operations](#privileged-operations) below for how this is packaged and its
  current limitations.

### Hook Management
- **List hooks** per repository with enabled/disabled status indicators.
- **Template library** with built-in hook scripts:
  - `pre-commit-msg-check` — reject commits with empty or too-short messages.
  - `post-commit-email` — send email notification after each commit.
  - `pre-commit-size-limit` — reject files exceeding a configurable size limit.
- **Install, enable, and disable** hooks with a single click.
- **Edit hook content** with syntax-highlighted code editor.

### Service Configuration
- Display current `svnserve` service status via `systemctl` (read-only, no privilege required).
- Copyable systemd unit file template for `svnserve`, plus a guided one-click install.
- Start/stop/restart the service directly from the app (via the PolicyKit-authorized helper — see
  [Privileged Operations](#privileged-operations)).

### Backup & Export
- **Dump** repositories (`svnadmin dump`) with progress feedback — full or incremental.
- **Load** dump files into repositories (`svnadmin load`).
- **Hot copy** for live backups (`svnadmin hotcopy`).
- **Cron template generator** — select a frequency and get a ready-to-use crontab line.

### General
- Light and dark theme support (auto-detects system preference).
- Keyboard shortcuts for all primary operations.
- Credential storage via OS keyring (GNOME Keyring / KDE Wallet) — no plaintext passwords.
- Window geometry persistence between sessions.

## Prerequisites

- **Python 3.10+**
- **Subversion 1.10+** CLI tools: `svnadmin`, `svnlook`, `svnserve`, `svn`
- **Linux** desktop environment (X11 or Wayland)
- **PolicyKit** (`pkexec`) — required for repository creation, service control, and any write to
  `/etc/svn/*` or systemd unit files (see [Privileged Operations](#privileged-operations))
- Appropriate **filesystem permissions** on the repository root directory

## Installation

### Quick Run (recommended — uses virtual environment)

From the workspace root, every `make` target auto-creates a `.venv/` and installs dependencies:

```bash
make run-server    # Creates .venv on first run, then launches the GUI
```

### Development Install (editable mode inside .venv)

```bash
# From workspace root — installs with dev dependencies into .venv
make dev-server

# Or manually (after make venv)
.venv/bin/pip install -e svn_server[dev]
```

### Production Install (from wheel)

```bash
# Build the wheel first (from workspace root)
make build-server

# Install the wheel into any Python environment
pip install svn_server/dist/svn_server_admin-0.1.0-py3-none-any.whl
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
# Via console script (available after make dev-server)
svn-server-admin

# Via Python module (using the venv)
.venv/bin/python -m svn_server
```

### Development Mode (without editable install)

```bash
# From workspace root — auto-creates .venv if needed
./scripts/run-dev.sh server

# Or via make
make run-server

# Or manually
PYTHONPATH=. .venv/bin/python -m svn_server
```

### First Launch

1. The application opens with an empty repository list.
2. Go to **File → Set Repository Root** (or press `Ctrl+O`) and select the directory that contains your SVN repositories (e.g. `/var/svn` or `/home/user/svn-repos`).
3. Repositories in that directory will appear in the left panel.
4. Select a repository to see its details, config, access control, hooks, and backup options in the right panel.

## Project Structure

```
svn_server/
├── __init__.py           # Package init, version string
├── __main__.py           # Entry point (svn-server-admin command)
├── app.py                # ServerMainWindow — main window, menus, toolbar, layout,
│                          #   startup provisioning checks (firewall, group membership)
├── repo_manager.py        # Repository list + create/delete/import/hotcopy dialogs,
│                          #   plus global Users/Groups tabs (centralized passwd/authz)
├── access_editor.py       # Per-repo tabbed editor: Repo Info, Users, Permissions, Server Config
├── hook_manager.py        # Hook list + template library + code editor
├── effective_access.py    # Effective-access evaluator (username + path → resulting rights)
├── smtp_manager.py        # Named SMTP profile manager, used by job notifications
├── backup_panel.py        # Dump/load/hotcopy UI + backup retention
├── job_scheduler.py       # Scheduled backup/verify jobs + crontab line generator
├── service_panel.py       # Service status/control (systemctl, pkexec) + performance settings
├── settings_dialog.py     # App settings: theme, repo root, password policy, global passwd/authz paths
├── pyproject.toml         # PEP 621 project metadata and build config
├── resources/
│   ├── hook_templates/    # Built-in hook script templates (.sh files)
│   │   ├── pre-commit-msg-check.sh
│   │   ├── post-commit-email.sh
│   │   └── pre-commit-size-limit.sh
│   ├── icons/                                    # Application icons
│   ├── system-helper.sh                          # Root-run privileged helper (see below)
│   ├── privileged_config_writer.py               # Writes passwd/authz/svnserve.conf as root
│   ├── org.svnsuite.svnserveradmin.policy.xml     # PolicyKit action declaration
│   └── svn_setup_command_ubuntu.sh                # Reference-only manual setup walkthrough
├── debian/                # .deb packaging; also installs the helper + polkit policy (see rules)
├── flatpak/               # Flatpak manifest — see the warning in Privileged Operations below
├── tests/
│   └── __init__.py        # Server UI tests (none written yet — svn_shared has the test suite)
└── README.md              # This file
```

All modules listed above are implemented and wired into `app.py`.

## Privileged Operations

Repositories, `/etc/svn/passwd`, `/etc/svn/authz`, and the `svnserve` systemd service are owned by a
dedicated `svn` user / `svnserver` group, not the desktop user running this app. Rather than requiring
the whole application to run as root, privileged actions are delegated to a small root-run helper
script (`resources/system-helper.sh`) authorized per-call via **PolicyKit** (`pkexec`):

- Repository create/delete, ownership fixes ("Fix Permissions")
- Writing `/etc/svn/passwd`, `/etc/svn/authz`, and per-repository `conf/` files (batched across
  repositories where possible, so one PolicyKit prompt can update several repos at once)
- `svnserve` service start/stop/restart and systemd unit installation
- Creating the `svnserver` group / `svn` user and adding the current user to the group
- Adding a firewall rule for SVN's port (3690/tcp) via `ufw`, if present

On a `.deb` install, the helper is placed at `/usr/bin/svn-server-admin-helper` and the PolicyKit
policy at `/usr/share/polkit-1/actions/`. **The Flatpak manifest has not yet been updated for this and
does not install either file** — privileged operations (repo creation, service control, settings that
write to `/etc/svn/`) are expected to fail or silently no-op in a Flatpak build until that manifest is
revisited. Prefer the `.deb` package if you need these features today.

## Testing

```bash
# Run server tests only (uses .venv automatically)
make test-server

# Run all tests (shared + client + server)
make test-all

# Run with verbose output
PYTHONPATH=. .venv/bin/python -m pytest svn_server/tests/ -v
```

## Configuration

Settings are stored via `QSettings` at `~/.config/svn-server-admin/settings.ini`:

```ini
[General]
theme=auto          # "light", "dark", or "auto"

[Server]
repo_root=/var/svn              # Default repository root directory
default_backend=fsfs
global_passwd_file=/etc/svn/passwd  # Centralized password database, shared by all repositories
global_authz_file=/etc/svn/authz    # Centralized group roster (per-repo path rules stay local)
```

## Shared Library

This application depends on `svn_shared/` for all SVN operations, config parsing, credential management, and shared widgets. At build time, `svn_shared/` is vendored into the package — there is no separate shared library to install.

## License

LGPL-3.0-or-later
