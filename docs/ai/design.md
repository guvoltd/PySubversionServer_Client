# Design — SVN Desktop Suite (Linux)

> **Agent**: Design Agent | **Version**: 1.1.0 | **Date**: 2026-04-30
> **Status**: MVP Architecture (Revised — Two Separate Apps) — Ready for Code Task Breakdown

---

## 1. Architecture Overview

The suite consists of **two independent applications** that share a common library, all developed within one workspace.

```
┌─────────────────────────────────────────────────────────────────┐
│                        WORKSPACE ROOT                           │
├────────────────────┬──────────────────────┬─────────────────────┤
│   svn_client/      │   svn_server/        │   svn_shared/       │
│   (App 1)          │   (App 2)            │   (Common Library)  │
│                    │                      │                     │
│ ┌────────────────┐ │ ┌──────────────────┐ │ ┌─────────────────┐ │
│ │ Client UI      │ │ │ Server Admin UI  │ │ │ SvnCommandRunner│ │
│ │ (QMainWindow)  │ │ │ (QMainWindow)    │ │ │ CredentialMgr   │ │
│ │                │ │ │                  │ │ │ SvnClientSvc    │ │
│ │ StatusTree     │ │ │ RepoManager      │ │ │ SvnAdminSvc     │ │
│ │ DiffViewer     │ │ │ AccessEditor     │ │ │ ConfigParser    │ │
│ │ LogViewer      │ │ │ HookManager      │ │ │ HookTemplates   │ │
│ │ CommitDialog   │ │ │ ServicePanel     │ │ │                 │ │
│ │ BranchDialog   │ │ │ BackupPanel      │ │ │ Shared Widgets  │ │
│ │ ConflictPanel  │ │ │                  │ │ │ (syntax hl,     │ │
│ │                │ │ │                  │ │ │  progress,      │ │
│ │                │ │ │                  │ │ │  search bar)    │ │
│ └───────┬────────┘ │ └───────┬──────────┘ │ └────────┬────────┘ │
│         │          │         │            │          │          │
│         └──────────┴─────────┴────imports──┘          │          │
│                                                       │          │
├───────────────────────────────────────────────────────┘          │
│                   Platform Layer                                 │
│  ┌────────────┐ ┌──────────────┐ ┌───────────────────┐          │
│  │QSettings   │ │Keyring       │ │SystemdIntegration │          │
│  │(per-app)   │ │(Secret Svc)  │ │(server only)      │          │
│  └────────────┘ └──────────────┘ └───────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

**Key change from v1.0**: Client and Server are **separate applications** with separate packages. They share `svn_shared/` which is vendored into each package at build time.

---

## 2. Module Decomposition

### 2.1 Package Structure

```
./                               # Workspace root
├── svn_shared/                  # Shared library (vendored into both apps)
│   ├── __init__.py
│   ├── svn_command.py           # Async subprocess runner
│   ├── svn_client_svc.py        # Client operations wrapper
│   ├── svn_admin_svc.py         # Admin operations wrapper
│   ├── credential_mgr.py        # keyring integration
│   ├── config_parser.py         # svnserve.conf / authz / passwd parsing
│   ├── hook_templates.py        # Built-in hook script templates
│   ├── exceptions.py            # Shared typed exceptions
│   ├── widgets/                 # Reusable Qt widgets (shared)
│   │   ├── __init__.py
│   │   ├── syntax_highlighter.py
│   │   ├── progress_overlay.py
│   │   └── search_bar.py
│   ├── resources/               # Shared resources
│   │   ├── icons/
│   │   └── styles/
│   │       ├── light.qss
│   │       └── dark.qss
│   └── tests/                   # Tests for shared library
│       ├── __init__.py
│       ├── test_svn_command.py
│       ├── test_svn_client_svc.py
│       ├── test_svn_admin_svc.py
│       ├── test_config_parser.py
│       └── test_credential_mgr.py
│
├── svn_client/                  # SVN Client application
│   ├── __init__.py
│   ├── __main__.py              # Entry point: svn-client
│   ├── app.py                   # QApplication setup, main window
│   ├── client_view.py           # Main window layout
│   ├── checkout_dialog.py       # Checkout wizard
│   ├── commit_dialog.py         # Commit dialog with file selector
│   ├── status_tree.py           # Working copy status tree widget
│   ├── diff_viewer.py           # Side-by-side / unified diff
│   ├── log_viewer.py            # Revision log table + detail
│   ├── branch_dialog.py         # Branch/tag create + switch
│   ├── conflict_panel.py        # Conflict resolution guidance
│   ├── resources/               # Client-specific resources
│   │   ├── icons/
│   │   └── hook_templates/      # (empty — client doesn't manage hooks)
│   ├── tests/                   # Client UI tests
│   │   ├── __init__.py
│   │   ├── test_status_tree.py
│   │   ├── test_diff_viewer.py
│   │   └── test_commit_dialog.py
│   ├── pyproject.toml           # Client package metadata
│   ├── Makefile                 # Client-specific build targets
│   ├── flatpak/
│   │   └── org.svnsuite.SvnClient.yml
│   └── debian/
│       ├── control
│       ├── rules
│       └── changelog
│
├── svn_server/                  # SVN Server Admin application
│   ├── __init__.py
│   ├── __main__.py              # Entry point: svn-server-admin
│   ├── app.py                   # QApplication setup, main window
│   ├── server_view.py           # Main window layout
│   ├── repo_manager.py          # Create/list/delete repos
│   ├── access_editor.py         # authz + passwd file editor
│   ├── hook_manager.py          # Hook template library + editor
│   ├── service_panel.py         # svnserve/Apache guidance
│   ├── backup_panel.py          # Dump/load/hotcopy UI
│   ├── resources/               # Server-specific resources
│   │   ├── icons/
│   │   └── hook_templates/
│   │       ├── pre-commit-msg-check.sh
│   │       ├── post-commit-email.sh
│   │       └── pre-commit-size-limit.sh
│   ├── tests/                   # Server UI tests
│   │   ├── __init__.py
│   │   ├── test_repo_manager.py
│   │   ├── test_access_editor.py
│   │   └── test_hook_manager.py
│   ├── pyproject.toml           # Server package metadata
│   ├── Makefile                 # Server-specific build targets
│   ├── flatpak/
│   │   └── org.svnsuite.SvnServerAdmin.yml
│   └── debian/
│       ├── control
│       ├── rules
│       └── changelog
│
├── Makefile                     # Top-level: builds BOTH projects
├── scripts/                     # Workspace-level build/deploy scripts
│   ├── build-all.sh             # Build both packages
│   ├── package-client-flatpak.sh
│   ├── package-client-deb.sh
│   ├── package-server-flatpak.sh
│   ├── package-server-deb.sh
│   └── run-dev.sh               # Dev launcher (pick client or server)
└── docs/kiro/                   # This documentation system
```

### 2.2 Build & Project Files (workspace root)

```
./
├── Makefile                     # Top-level orchestrator
│                                #   make build-all
│                                #   make build-client / make build-server
│                                #   make test-all
│                                #   make package-all
├── svn_client/pyproject.toml    # Client PEP 621 metadata
├── svn_client/Makefile          # Client-specific targets
├── svn_server/pyproject.toml    # Server PEP 621 metadata
├── svn_server/Makefile          # Server-specific targets
├── svn_client/flatpak/          # Client Flatpak manifest
├── svn_server/flatpak/          # Server Flatpak manifest
├── svn_client/debian/           # Client .deb packaging
├── svn_server/debian/           # Server .deb packaging
├── scripts/                     # Workspace-level build/deploy scripts
│   ├── build-all.sh
│   ├── package-client-flatpak.sh
│   ├── package-client-deb.sh
│   ├── package-server-flatpak.sh
│   ├── package-server-deb.sh
│   └── run-dev.sh
└── docs/kiro/                   # This documentation system
```

---

## 3. Key Design Decisions

### 3.1 Two Separate Applications, Shared Library

The Client and Server Admin are **independent applications** with their own `QMainWindow`, entry point, and package. They share a common `svn_shared/` library that is vendored into each package at build time. Rationale:
- Different user roles install different tools — developers don't need server admin, admins may not need the client GUI.
- Independent release cycles — a client bugfix doesn't require re-releasing the server package.
- Shared code (SvnCommandRunner, CredentialManager, widgets) avoids duplication without coupling the packages at runtime.
- Each app has its own `QSettings` namespace (`svn-client` / `svn-server-admin`).

### 3.2 Async Command Execution

All SVN CLI calls run in `QThread` workers via `SvnCommandRunner` (from `svn_shared`). This keeps the UI responsive during long operations (checkout, dump, update). The runner:
- Uses `subprocess.Popen` with stdout/stderr pipes.
- Emits Qt signals for progress, completion, and errors.
- Supports cancellation via `process.terminate()`.

```python
class SvnCommandRunner(QObject):
    output_line = Signal(str)
    finished = Signal(int, str)    # exit_code, full_output
    error = Signal(str)

    def run(self, args: list[str], cwd: str | None = None) -> None:
        """Execute svn command in a worker thread."""
        ...
```

### 3.3 Service Layer Separation

The `svn_shared/` package contains the service layer. Services that need Qt signals (like `SvnCommandRunner`) import only `PySide6.QtCore` (signals/slots), never widgets. Pure business logic modules (`config_parser.py`, `credential_mgr.py`) have zero Qt imports. This enables:
- Unit testing without a display server (no QApplication needed).
- Potential reuse as a CLI library.
- Clean separation of concerns.
- Vendoring into both app packages without widget conflicts.

### 3.4 Config File Parsing

SVN config files (`svnserve.conf`, `authz`, `passwd`) use INI-like formats. The `config_parser.py` module provides read/write with:
- Preservation of comments and ordering.
- Validation before write.
- Backup of original file before modification.

### 3.5 Diff Viewer Architecture

The diff viewer uses a custom `QPlainTextEdit` subclass with:
- Line-number gutter.
- Syntax highlighting via `QSyntaxHighlighter`.
- Color-coded additions (green), deletions (red), context (gray).
- Synchronized scrolling for side-by-side mode.
- Toggle between unified and side-by-side views.

---

## 4. UI Wireframes (Text)

### 4.1 SVN Client — Main Window Layout

```
┌──────────────────────────────────────────────────────────┐
│ [Menu Bar]  File  Edit  View  SVN  Tools  Help           │
├──────────────────────────────────────────────────────────┤
│ [Toolbar] 🔄Update  ✅Commit  📋Log  🔀Branch  ⚙Settings│
├────────────────┬─────────────────────────────────────────┤
│                │                                         │
│  File Tree     │   Content Area                          │
│  (status       │   (diff view / log table /              │
│   icons)       │    commit dialog / etc.)                │
│                │                                         │
│  [M] src/      │   --- a/src/main.py                     │
│  [A] new.py    │   +++ b/src/main.py                     │
│  [?] draft.txt │   @@ -10,3 +10,5 @@                    │
│  [C] config.py │   -old_line                             │
│                │   +new_line                              │
│                │   +another_line                          │
│                │                                         │
├────────────────┴─────────────────────────────────────────┤
│ [Status Bar]  Working Copy: /home/user/project  Rev: 142 │
└──────────────────────────────────────────────────────────┘
```

### 4.2 SVN Server Admin — Main Window Layout

```
┌──────────────────────────────────────────────────────────┐
│ [Menu Bar]  File  Edit  View  Admin  Tools  Help         │
├──────────────────────────────────────────────────────────┤
│ [Toolbar] ➕Create  🗑Delete  🔄Refresh  💾Backup  ⚙Settings│
├──────────────┬───────────────────────────────────────────┤
│              │                                           │
│ Repositories │  Repository: my-project                   │
│ ─────────────│  UUID: a1b2c3d4-...                       │
│ ▶ my-project │  HEAD Rev: 342                            │
│   my-libs    │  Backend: FSFS                            │
│   archive    │  Size: 128 MB                             │
│              │                                           │
│ [+ Create]   │  ┌─────────┬──────────┬────────┬───────┐ │
│ [🗑 Delete]  │  │ Config  │ Access   │ Hooks  │Backup │ │
│              │  ├─────────┴──────────┴────────┴───────┤ │
│              │  │                                     │ │
│              │  │  (Sub-tab content area)              │ │
│              │  │                                     │ │
│              │  └─────────────────────────────────────┘ │
├──────────────┴───────────────────────────────────────────┤
│ [Status Bar]  Repo Root: /var/svn  Repos: 3              │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Data Flow Diagrams

### 5.1 Commit Flow

```
User clicks Commit
       │
       ▼
CommitDialog opens
  ├── SvnClientSvc.status(wc_path) → file list with statuses
  ├── User selects files, writes message
  └── User clicks OK
       │
       ▼
SvnClientSvc.commit(wc_path, files, message)
       │
       ▼
SvnCommandRunner.run(["svn", "commit", "-m", msg, ...files])
       │
       ├── Signal: output_line → progress in status bar
       ├── Signal: finished(0, output) → success notification
       └── Signal: error(msg) → error dialog
```

### 5.2 Repository Create Flow

```
Admin clicks Create Repository
       │
       ▼
CreateRepoDialog opens
  ├── User enters: name, backend (FSFS/FSX), layout (standard/flat)
  └── User clicks Create
       │
       ▼
SvnAdminSvc.create_repo(root_path, name, backend)
       │
       ▼
SvnCommandRunner.run(["svnadmin", "create", "--fs-type", backend, path])
       │
       ├── If standard layout requested:
       │   SvnCommandRunner.run(["svn", "mkdir", url+"/trunk", url+"/branches", url+"/tags", "-m", "Initial structure"])
       │
       ├── Signal: finished(0) → refresh repo list, show success
       └── Signal: error → show error dialog
```

---

## 6. Integration Points

### 6.1 Existing Build/Deploy Scripts

The applications provide integration without replacing existing tooling:

| Integration Point | Mechanism |
|---|---|
| CLI entry points | `svn-client` and `svn-server-admin` console_scripts (separate) |
| Post-commit hook trigger | Hook templates can call existing deploy scripts |
| Exit codes | All CLI operations return standard exit codes for scripting |
| Environment variables | `SVN_CLIENT_WC_PATH` for client; `SVN_SERVER_REPO_ROOT` for server |
| Top-level Makefile | `make build-all`, `make build-client`, `make build-server`, `make test-all`, `make package-all` |
| Per-project Makefile | Each project has its own `make build`, `make test`, `make package-flatpak`, `make package-deb` |

### 6.2 Assumptions About Existing Workspace

Since the workspace is currently empty, the design assumes:
- Build scripts (if they exist) are in `./scripts/` or at the workspace root.
- The top-level `Makefile` orchestrates building both projects and can call existing scripts.
- Each project (`svn_client/`, `svn_server/`) has its own `Makefile` for independent builds.
- No existing Python project structure to conflict with.

---

## 7. Security Design

| Concern | Mitigation |
|---|---|
| Credential storage | `keyring` library → Secret Service D-Bus API (GNOME Keyring / KDE Wallet) |
| Subprocess injection | All CLI args passed as list (never shell=True); paths validated |
| Config file writes | Atomic write (write to temp, rename); backup original first |
| Server admin privilege | Check filesystem permissions before operations; warn if insufficient |
| Hook script execution | Hooks run by SVN server, not by this app; app only edits files |

---

## 8. Theme & Styling

- Ship with `light.qss` and `dark.qss` stylesheets.
- Auto-detect system theme via `QPalette` at startup.
- User can override in Settings.
- Diff colors follow conventional green/red/blue scheme with sufficient contrast for accessibility (WCAG AA).

---

## 9. Settings Persistence

Use `QSettings` with INI backend. Each application has its own settings namespace:

**SVN Client** — stored at `~/.config/svn-client/settings.ini`:

```ini
[General]
theme=auto
last_wc_path=/home/user/project

[Client]
diff_mode=side-by-side
log_limit=500
show_unversioned=true
```

**SVN Server Admin** — stored at `~/.config/svn-server-admin/settings.ini`:

```ini
[General]
theme=auto

[Server]
repo_root=/var/svn
default_backend=fsfs
```

---

## 10. Error Handling Strategy

| Layer | Strategy |
|---|---|
| SvnCommandRunner | Capture stderr; emit `error` signal with parsed message |
| Service Layer | Raise typed exceptions (`SvnAuthError`, `SvnConflictError`, `SvnNotFoundError`) |
| UI Layer | Catch service exceptions; show `QMessageBox` with actionable guidance |
| Unhandled | Global exception hook logs to `~/.local/share/<app-name>/crash.log` and shows crash dialog |
