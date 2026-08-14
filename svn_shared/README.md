# SVN Shared

Common service library for the SVN Desktop Suite. This package provides all the backend logic, SVN CLI wrappers, configuration file parsers, credential management, and reusable Qt widgets shared between the **SVN Client** and **SVN Server Admin** applications.

This is **not a standalone application** — it is vendored (copied) into each application's package at build time. You do not install `svn_shared` separately.

## Architecture

```
svn_shared/
├── svn_command.py       ← Foundation: async subprocess wrapper
├── svn_client_svc.py    ← Client operations (used by svn_client)
├── svn_admin_svc.py     ← Admin operations (used by svn_server)
├── config_parser.py     ← SVN config file read/write
├── credential_mgr.py    ← OS keyring integration
├── hook_templates.py    ← Hook script template manager
├── exceptions.py        ← Shared exception hierarchy
├── widgets/             ← Reusable PySide6 widgets
│   ├── syntax_highlighter.py
│   ├── progress_overlay.py
│   └── search_bar.py
├── resources/styles/    ← QSS theme files
│   ├── light.qss
│   └── dark.qss
└── tests/               ← Unit tests (44 tests, all passing)
```

## Modules

### `svn_command.py` — SVN Command Runner

The foundation layer. All other services use this to execute SVN CLI commands.

| Function | Description |
|---|---|
| `run_sync(args, cwd, timeout)` | Run a command synchronously. Returns a `CommandResult` with exit code, stdout, stderr. |
| `run_async(args, cwd, on_line, on_finished, on_error)` | Run a command in a background thread. Calls `on_line` for each stdout line as it arrives. Returns a `RunningCommand` handle for cancellation. |
| `validate_args(args)` | Validate arguments — rejects empty lists and shell metacharacters (`;`, `|`, `` ` ``, `$`, etc.) to prevent injection. |

Key types:
- `CommandResult` — dataclass with `args`, `exit_code`, `stdout`, `stderr`, and a `success` property.
- `RunningCommand` — handle with `cancel()` method and `is_cancelled` property.

### `svn_client_svc.py` — SVN Client Service

Wraps `svn` CLI commands for working copy operations. All functions return structured dataclasses, not raw strings.

| Function | Description |
|---|---|
| `checkout(url, path, revision, username, password)` | Checkout a remote repository to a local path. |
| `update(path, revision)` | Update a working copy. |
| `commit(path, message, files)` | Commit changes. Returns the committed revision number. |
| `status(path)` | Get working copy status. Returns `list[StatusEntry]`. |
| `diff(path, revision, file)` | Get unified diff output as a string. |
| `log(path, limit, revision_range)` | Get revision log. Returns `list[LogEntry]`. |
| `add(paths, cwd)` | Add files to version control. |
| `remove(paths, cwd)` | Remove files from version control. |
| `revert(paths, recursive, cwd)` | Revert local changes. |
| `switch(path, url)` | Switch working copy to a different branch/tag. |
| `copy(src_url, dst_url, message)` | Server-side copy for branch/tag creation. |
| `info(path)` | Get working copy info. Returns `WCInfo`. |
| `resolve(path, file)` | Mark a conflicted file as resolved. |

Key types: `StatusEntry`, `LogEntry`, `ChangedPath`, `WCInfo`.

### `svn_admin_svc.py` — SVN Admin Service

Wraps `svnadmin` and `svnlook` CLI commands for repository management.

| Function | Description |
|---|---|
| `create_repo(root, name, fs_type, standard_layout)` | Create a new repository. Optionally creates trunk/branches/tags. |
| `list_repos(root)` | List all valid repositories under a root directory. Returns `list[RepoInfo]`. |
| `repo_info(path)` | Get metadata for a single repository (UUID, HEAD rev, fs-type, size). |
| `delete_repo(path, backup_first)` | Delete a repository. Optionally hot-copies to `.bak` first. |
| `dump(repo_path, output_file, incremental, lower_rev, upper_rev)` | Dump a repository to a file. |
| `load(repo_path, input_file)` | Load a dump file into a repository. |
| `hotcopy(repo_path, dest_path)` | Create a hot copy of a repository. |
| `verify(repo_path)` | Verify repository integrity. Returns `True` / `False`. |

Key types: `RepoInfo`.

### `config_parser.py` — SVN Config File Parser

Reads and writes SVN configuration files while preserving comments and ordering. Creates `.bak` backups before every write.

| Function | Description |
|---|---|
| `parse_svnserve_conf(path)` | Parse `svnserve.conf`. Returns `SvnserveConfig`. |
| `write_svnserve_conf(path, config)` | Write `svnserve.conf` with comment preservation. |
| `parse_authz(path)` | Parse `authz` file. Returns `list[AuthzRule]`. |
| `write_authz(path, rules)` | Write `authz` file from rules. |
| `parse_passwd(path)` | Parse `passwd` file. Returns `list[PasswdEntry]`. |
| `write_passwd(path, entries)` | Write `passwd` file. |

Key types: `SvnserveConfig`, `AuthzRule`, `PasswdEntry`.

### `credential_mgr.py` — Credential Manager

Stores and retrieves SVN credentials via the OS keyring (GNOME Keyring / KDE Wallet) using the `keyring` library. Never stores passwords in plaintext.

| Function | Description |
|---|---|
| `is_available()` | Check if a real keyring backend is available. |
| `store(realm, username, password)` | Store credentials for an SVN realm. |
| `retrieve(realm)` | Retrieve credentials. Returns `Credential` or `None`. |
| `delete(realm)` | Delete stored credentials for a realm. |

If the `keyring` library is not installed or no backend is available, all operations gracefully degrade (return `None` or log warnings) rather than crashing.

### `hook_templates.py` — Hook Template Manager

Manages SVN repository hook scripts — built-in templates, installation, and enable/disable lifecycle.

| Function | Description |
|---|---|
| `list_templates(extra_dir)` | List all available templates (built-in + optional directory). |
| `get_template(name)` | Get a specific built-in template by name. |
| `list_hooks(repo_path)` | List hooks in a repository with enabled/disabled status. |
| `install_hook(repo_path, hook_name, content)` | Write a hook script and make it executable. |
| `enable_hook(repo_path, hook_name)` | Enable a disabled hook (remove `.tmpl` suffix). |
| `disable_hook(repo_path, hook_name)` | Disable an active hook (add `.tmpl` suffix). |

Built-in templates: `pre-commit-msg-check`, `post-commit-email`, `pre-commit-size-limit`.

### `exceptions.py` — Exception Hierarchy

```
SvnSuiteError (base)
├── SvnCommandError        — SVN CLI command failed (has command, exit_code, stderr)
│   └── SvnAuthError       — Authentication/authorization failure
├── SvnConflictError       — Unresolved conflicts (has paths list)
├── SvnNotFoundError       — Working copy or repository not found
├── ConfigParseError       — Config file parse failure (has path, line, detail)
└── CredentialError        — Credential storage/retrieval failure
```

### `widgets/` — Reusable Qt Widgets

| Widget | Description |
|---|---|
| `DiffHighlighter` | `QSyntaxHighlighter` for unified diff output — green for additions, red for deletions, blue for hunk headers. |
| `ShellHighlighter` | `QSyntaxHighlighter` for bash/shell scripts — comments, strings, variables, keywords. |
| `ProgressOverlay` | Semi-transparent overlay with progress bar and status label. Call `show_progress()`, `set_progress()`, `hide_progress()`. |
| `SearchBar` | Search input with clear button. Emits `search_changed` and `search_submitted` signals. |

### `resources/styles/` — QSS Theme Files

- `light.qss` — Light theme stylesheet for all Qt widgets.
- `dark.qss` — Dark theme stylesheet with WCAG AA contrast ratios.

Both themes style: `QMainWindow`, `QMenuBar`, `QToolBar`, `QStatusBar`, `QTreeView`, `QTableView`, `QPlainTextEdit`, `QPushButton`, `QLineEdit`, `QTabWidget`, `QSplitter`.

## Testing

The shared library has 44 unit tests covering all service modules:

```bash
# From workspace root (uses .venv automatically)
make test-shared

# Or directly via the venv
PYTHONPATH=. .venv/bin/python -m pytest svn_shared/tests/ -v

# With coverage
make coverage
```

### Test Files

| File | Tests | What it covers |
|---|---|---|
| `test_svn_command.py` | 12 | Argument validation, sync/async execution, timeout, cancellation, injection prevention |
| `test_svn_client_svc.py` | 6 | XML parsing for status/log/info, commit revision extraction, auth error detection |
| `test_svn_admin_svc.py` | 9 | Repo create/list/info/delete, backup-before-delete, verify |
| `test_config_parser.py` | 7 | Round-trip parse/write for svnserve.conf, authz, passwd; comment preservation; backup creation |
| `test_credential_mgr.py` | 7 | Store/retrieve/delete with mock keyring; graceful fallback when keyring unavailable |

All tests use mocked subprocess calls — they do not require SVN CLI tools or a display server to run.

## Usage in Application Code

```python
# In svn_client or svn_server code:
from svn_shared.svn_client_svc import status, commit, log
from svn_shared.svn_admin_svc import create_repo, list_repos
from svn_shared.credential_mgr import store, retrieve
from svn_shared.config_parser import parse_authz, write_authz
from svn_shared.exceptions import SvnAuthError, SvnCommandError
from svn_shared.widgets.syntax_highlighter import DiffHighlighter
from svn_shared.widgets.progress_overlay import ProgressOverlay
```

## License

LGPL-3.0-or-later
