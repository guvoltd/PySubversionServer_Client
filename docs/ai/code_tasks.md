# Code Tasks — SVN Desktop Suite (Linux)

> **Agent**: Code Agent | **Version**: 1.1.0 | **Date**: 2026-04-30
> **Status**: MVP Task Breakdown (Revised — Two Separate Apps) — Ready for Implementation

---

## Task Legend

| Status | Meaning |
|---|---|
| ⬜ | Not started |
| 🔨 | In progress |
| ✅ | Complete |
| 🚫 | Blocked |

---

## Phase 0 — Project Scaffolding

### T-000: Initialize shared library structure ✅
- Create `svn_shared/` package with `__init__.py` and `exceptions.py`.
- No `pyproject.toml` for shared — it is vendored, not independently installable.
- Create `svn_shared/widgets/` with `__init__.py`.
- Create `svn_shared/resources/styles/` with placeholder QSS files.
- Create `svn_shared/tests/` with `__init__.py`.

### T-001: Initialize SVN Client project ✅
- Create `svn_client/` package with `__init__.py` and `__main__.py`.
- Create `svn_client/pyproject.toml` with PEP 621 metadata.
  - Dependencies: `PySide6>=6.7`, `keyring>=25.0`.
  - Dev dependencies: `pytest`, `pytest-qt`, `ruff`, `mypy`.
  - Console script entry point: `svn-client = svn_client.__main__:main`.
- Create `svn_client/Makefile` with per-project targets.
- Verify `python -m svn_client` launches without error.

### T-002: Initialize SVN Server Admin project ✅
- Create `svn_server/` package with `__init__.py` and `__main__.py`.
- Create `svn_server/pyproject.toml` with PEP 621 metadata.
  - Dependencies: `PySide6>=6.7`, `keyring>=25.0`.
  - Dev dependencies: `pytest`, `pytest-qt`, `ruff`, `mypy`.
  - Console script entry point: `svn-server-admin = svn_server.__main__:main`.
- Create `svn_server/Makefile` with per-project targets.
- Verify `python -m svn_server` launches without error.

### T-003: Top-level Makefile and build scripts ✅
- Top-level `Makefile` with orchestration targets:
  - `make build-all` — build both wheels.
  - `make build-client` / `make build-server` — build individually.
  - `make test-all` — run all tests (shared + client + server).
  - `make lint-all` — run ruff + mypy on all packages.
  - `make package-all` — build all Flatpak + .deb packages.
- `scripts/build-all.sh` — shell wrapper for CI.
- `scripts/package-client-flatpak.sh`, `scripts/package-client-deb.sh`.
- `scripts/package-server-flatpak.sh`, `scripts/package-server-deb.sh`.
- `scripts/run-dev.sh` — convenience launcher (accepts `client` or `server` arg).

### T-004: Resource files ✅
- Create `svn_shared/resources/styles/light.qss` and `dark.qss` with base styles.
- Create `svn_shared/resources/icons/` with placeholder SVG icons (status, toolbar).
- Create `svn_server/resources/hook_templates/` with 3 starter hook scripts.
- Create `svn_client/resources/icons/` with client-specific app icon.

---

## Phase 1 — Backend / Service Layer (No Qt) — in `svn_shared/`

### T-100: SvnCommandRunner ✅
- File: `svn_shared/svn_command.py`
- Async subprocess wrapper using `subprocess.Popen`.
- Methods: `run_sync(args, cwd)`, `run_async(args, cwd, callback)`.
- Output capture (stdout + stderr), exit code, timeout support.
- Cancellation via `process.terminate()`.
- Input validation: reject shell metacharacters in arguments.
- **Test**: `svn_shared/tests/test_svn_command.py` — mock subprocess, verify arg passing.

### T-101: SVN Client Service ✅
- File: `svn_shared/svn_client_svc.py`
- Methods mapping to SVN operations:
  - `checkout(url, path, revision=None)`
  - `update(path, revision=None)`
  - `commit(path, message, files=None)`
  - `status(path)` → list of `(path, status_code)` tuples
  - `diff(path, revision=None)` → unified diff string
  - `log(path, limit=100, revision_range=None)` → list of log entries
  - `add(paths)`, `remove(paths)`, `revert(paths)`
  - `switch(path, url)`
  - `copy(src_url, dst_url, message)` — for branch/tag
  - `info(path)` → dict of working copy info
  - `resolve(path)` — mark conflict resolved
- All methods return structured data (dataclasses), not raw strings.
- **Test**: `svn_shared/tests/test_svn_client_svc.py` — mock SvnCommandRunner.

### T-102: SVN Admin Service ✅
- File: `svn_shared/svn_admin_svc.py`
- Methods:
  - `create_repo(root, name, fs_type='fsfs')`
  - `list_repos(root)` → list of repo info dicts
  - `repo_info(path)` → dict (UUID, HEAD rev, fs-type)
  - `delete_repo(path, backup_first=True)`
  - `dump(repo_path, output_file, incremental=False)`
  - `load(repo_path, input_file)`
  - `hotcopy(repo_path, dest_path)`
  - `verify(repo_path)`
- **Test**: `svn_shared/tests/test_svn_admin_svc.py` — mock SvnCommandRunner.

### T-103: Config File Parser ✅
- File: `svn_shared/config_parser.py`
- Parse and write: `svnserve.conf`, `authz`, `passwd`.
- Preserve comments and whitespace.
- Dataclasses for structured representation:
  - `SvnserveConfig(anon_access, auth_access, password_db, authz_db, realm)`
  - `AuthzRule(path, user, permission)`
  - `PasswdEntry(username, password_hash)`
- Atomic write with backup.
- **Test**: `svn_shared/tests/test_config_parser.py` — round-trip parse/write.

### T-104: Credential Manager ✅
- File: `svn_shared/credential_mgr.py`
- Uses `keyring` library.
- Methods:
  - `store(realm, username, password)`
  - `retrieve(realm)` → `(username, password)` or None
  - `delete(realm)`
  - `list_realms()` → list of stored realm names
- Fallback: if keyring unavailable, warn user (no plaintext fallback).
- **Test**: `svn_shared/tests/test_credential_mgr.py` — mock keyring backend.

### T-105: Hook Template Manager ✅
- File: `svn_shared/hook_templates.py`
- Load built-in templates from `svn_server/resources/hook_templates/`.
- Methods:
  - `list_templates()` → list of `(name, description, content)`
  - `get_template(name)` → template content string
  - `install_hook(repo_path, hook_name, content)` — write + chmod +x
  - `list_hooks(repo_path)` → list of `(name, enabled, path)`
  - `enable_hook(repo_path, name)` / `disable_hook(repo_path, name)`
- **Test**: `svn_shared/tests/test_hook_templates.py` — temp directory fixtures.

---

## Phase 2 — Qt UI Shells (One Per Application)

### T-200: SVN Client Main Window & Application ✅
- File: `svn_client/app.py`
- `QApplication` setup with organization="svnsuite", app name="svn-client" for `QSettings`.
- `ClientMainWindow(QMainWindow)` with:
  - Menu bar (File, Edit, View, SVN, Tools, Help).
  - Toolbar with client actions (Update, Commit, Log, Branch, Settings).
  - Central widget: splitter with file tree + content area.
  - Status bar with working copy info.
- Theme loading from shared QSS files; auto-detect system preference.

### T-201: SVN Server Admin Main Window & Application ✅
- File: `svn_server/app.py`
- `QApplication` setup with organization="svnsuite", app name="svn-server-admin" for `QSettings`.
- `ServerMainWindow(QMainWindow)` with:
  - Menu bar (File, Edit, View, Admin, Tools, Help).
  - Toolbar with admin actions (Create, Delete, Refresh, Backup, Settings).
  - Central widget: splitter with repo list + detail area.
  - Status bar with repo root info.
- Theme loading from shared QSS files.

### T-202: Settings Dialogs (one per app) ⬜
- **Client Settings**: theme selector, default working copy path, diff mode, log limit, show unversioned toggle.
- **Server Settings**: theme selector, repository root path, default backend.
- Both persist via `QSettings` in their respective namespaces.

---

## Phase 3 — SVN Client UI (in `svn_client/`)

### T-300: Status Tree Widget ⬜
- File: `svn_client/status_tree.py`
- `QTreeView` with custom model showing file tree.
- Status icons: Modified (M), Added (A), Deleted (D), Conflicted (C), Unversioned (?).
- Context menu: Add, Remove, Revert, Diff, Log for selected file.
- Checkbox column for commit file selection.
- Refresh on demand and after operations.

### T-301: Diff Viewer ⬜
- File: `svn_client/diff_viewer.py`
- Two modes: side-by-side (`QSplitter` with two `QPlainTextEdit`) and unified.
- Syntax highlighting for diff hunks (green/red/blue).
- Line number gutter.
- Synchronized scrolling in side-by-side mode.
- Toolbar: toggle mode, copy, font size.

### T-302: Log Viewer ⬜
- File: `svn_client/log_viewer.py`
- `QTableView` with columns: Revision, Author, Date, Message (truncated).
- Detail panel below table showing full message + changed paths.
- Search/filter bar: by author, date range, message text.
- Double-click revision → show diff.
- Pagination: load more on scroll.

### T-303: Checkout Dialog ⬜
- File: `svn_client/checkout_dialog.py`
- Fields: Repository URL, local path (with browse button), revision (HEAD or specific).
- URL validation (svn://, http://, https://, file://).
- Progress feedback during checkout.
- Credential prompt if auth required.

### T-304: Commit Dialog ⬜
- File: `svn_client/commit_dialog.py`
- File list with checkboxes (pre-populated from status).
- Multi-line message editor with spell-check placeholder.
- Recent messages dropdown.
- Diff preview for selected file.
- Commit button disabled until message entered and files selected.

### T-305: Branch/Tag Dialog ⬜
- File: `svn_client/branch_dialog.py`
- Two modes: Create Branch/Tag and Switch.
- Create: source URL, destination URL (auto-suggest from standard layout), message.
- Switch: dropdown/tree of available branches and tags.
- Standard layout detection (trunk/branches/tags).

### T-306: Conflict Resolution Panel ⬜
- File: `svn_client/conflict_panel.py`
- List conflicted files with conflict type.
- For each file: show mine/theirs/base versions.
- Buttons: Use Mine, Use Theirs, Edit Manually (launch external editor), Mark Resolved.
- Guidance text explaining each conflict type.

---

## Phase 4 — SVN Server Admin UI (in `svn_server/`)

### T-400: Repository Manager ⬜
- File: `svn_server/repo_manager.py`
- Left panel: `QListWidget` of repositories.
- Right panel: repo info display.
- Create dialog: name, backend selector, standard layout checkbox.
- Delete with confirmation dialog and optional backup.
- Refresh button.

### T-401: Access Control Editor ⬜
- File: `svn_server/access_editor.py`
- Tab 1 — Users (`passwd` file): table with add/edit/remove.
- Tab 2 — Permissions (`authz` file): path-based permission matrix.
  - Rows: repository paths.
  - Columns: users/groups.
  - Cells: r, rw, or deny.
- Tab 3 — Server config (`svnserve.conf`): form with dropdowns.
- Save button with validation and backup.

### T-402: Hook Manager ⬜
- File: `svn_server/hook_manager.py`
- Left: list of hooks for selected repo (with enabled/disabled indicator).
- Right: code editor (`QPlainTextEdit` with syntax highlighting) for hook content.
- Template library: dropdown to insert from built-in templates.
- Enable/disable toggle.
- Test button (dry-run with sample data).

### T-403: Service Configuration Panel ⬜
- File: `svn_server/service_panel.py`
- Display current svnserve/Apache status (via `systemctl`).
- Guidance cards:
  - svnserve systemd unit file template (copyable).
  - Apache mod_dav_svn config snippet (copyable).
- Start/stop/restart buttons (with privilege warning).

### T-404: Backup Panel ⬜
- File: `svn_server/backup_panel.py`
- Dump: select repo, output file path, incremental toggle, progress bar.
- Load: select repo, input file path, progress bar.
- Hotcopy: select repo, destination path.
- Cron template generator: frequency selector → crontab line (copyable).

---

## Phase 5 — Packaging & Distribution (Separate Packages)

### T-500: Client Flatpak manifest ⬜
- File: `svn_client/flatpak/org.svnsuite.SvnClient.yml`
- Runtime: `org.kde.Platform` (includes Qt 6).
- Permissions: filesystem access, network (for SVN), D-Bus (for keyring).
- Build steps: vendor `svn_shared/` into package, pip install from source.

### T-501: Server Flatpak manifest ⬜
- File: `svn_server/flatpak/org.svnsuite.SvnServerAdmin.yml`
- Runtime: `org.kde.Platform` (includes Qt 6).
- Permissions: filesystem access, D-Bus (for keyring).
- Build steps: vendor `svn_shared/` into package, pip install from source.

### T-502: Client Debian packaging ⬜
- Files: `svn_client/debian/control`, `debian/rules`, `debian/changelog`.
- Package name: `svn-client`.
- Dependencies: `python3-pyside6`, `subversion`, `python3-keyring`.
- Build with `dpkg-buildpackage`.

### T-503: Server Debian packaging ⬜
- Files: `svn_server/debian/control`, `debian/rules`, `debian/changelog`.
- Package name: `svn-server-admin`.
- Dependencies: `python3-pyside6`, `subversion`, `python3-keyring`.
- Build with `dpkg-buildpackage`.

### T-504: Desktop integration (both apps) ⬜
- `.desktop` file for each application launcher.
- AppStream metadata XML for each app.
- Application icons (SVG, multiple sizes) — distinct icons for client vs server.

---

## Phase 6 — Polish & Integration

### T-600: Keyboard shortcuts ⬜
- Define shortcut map for all primary operations.
- Configurable via Settings.
- Shortcut hints in tooltips and menus.

### T-601: Error handling & logging ⬜
- Global exception handler with crash dialog (per app).
- Structured logging to `~/.local/share/<app-name>/<app-name>.log`.
- Log rotation (keep last 5 files, 1 MB each).

### T-602: Build/deploy script integration ⬜
- Document environment variables for script integration.
- Ensure top-level `Makefile` targets can call existing workspace scripts.
- Ensure per-project `Makefile` targets work independently.
- Provide hook templates that reference common CI/deploy patterns.

### T-603: Shared library vendoring ⬜
- Build script copies `svn_shared/` into each app's package directory before wheel/package build.
- Verify both apps work with vendored shared code (no workspace-level imports at runtime).
- Document the vendoring process in `scripts/build-all.sh`.

---

## Dependency Summary

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 (Client UI) ──→ Phase 5 (Client pkg)
                │            └──→ Phase 4 (Server UI) ──→ Phase 5 (Server pkg)
                └──→ (tests run continuously)
Phase 5 ──→ Phase 6
```

All Phase 1 tasks are independent of each other and can be parallelized.
Phase 2 produces two independent UI shells (T-200 for client, T-201 for server) — these can be parallelized.
Phase 3 and Phase 4 depend on their respective Phase 2 shell and Phase 1 (services).
Phase 3 and Phase 4 are independent of each other and can be parallelized.
Phase 5 produces separate packages for each app — client and server packaging can be parallelized.
