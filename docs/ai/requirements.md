# Requirements — SVN Desktop Suite (Linux)

> **Agent**: Requirement Agent | **Version**: 1.1.0 | **Date**: 2026-04-30
> **Status**: MVP Draft (Revised) — Ready for Design Review

---

## 1. Product Vision

Two **separate** Linux desktop applications — an **SVN Client** (developer-facing) and an **SVN Server Admin** (ops-facing) — developed within a single workspace but built, packaged, and distributed as independent installable packages. Each application has its own entry point, its own Flatpak/.deb package, and can be installed independently. They share a common service library extracted into a shared internal package within the workspace.

The goal is to replace fragmented CLI workflows with discoverable, keyboard-friendly graphical tools that integrate with existing build/deploy infrastructure. Keeping both projects in one workspace enables code reuse (SVN command runner, credential manager) while respecting the operational reality that developers and admins install different tools.

---

## 2. Stakeholders

| Role | Needs |
|---|---|
| Developer | Fast checkout/commit/diff/log, conflict resolution, credential management |
| DevOps / Admin | Repo creation, access control, hook management, backup guidance |
| Release Engineer | Branch/tag operations, integration with CI scripts |
| Security | Credential storage via OS keyring, no plaintext secrets |

---

## 3. Technology Decisions & Rationale

### 3.1 GUI Framework — **PySide6 (Qt 6 for Python)**

| Criterion | PySide6 | PyQt6 | GTK 4 (PyGObject) |
|---|---|---|---|
| License | **LGPL v3** — allows proprietary distribution | GPL v3 — requires open-sourcing or commercial license | LGPL but ecosystem fragmented |
| Widget richness | Excellent (tree views, diffs, docks) | Same Qt widgets | Fewer advanced widgets |
| Designer tooling | Qt Designer / Qt Creator | Same | Glade (less maintained) |
| Cross-desktop look | Native on KDE; acceptable on GNOME via qt6ct | Same | Native GNOME only |
| Python ecosystem | Official Qt Company bindings | Third-party (Riverbank) | Stable but smaller community |

**Decision**: PySide6. The LGPL license gives maximum flexibility for open-source *and* potential commercial distribution without a separate license purchase. Qt 6 provides the rich widget set needed for tree views, diff viewers, and dockable panels.

*Sources*:
- [PySide6 vs PyQt6 licensing — pythonguis.com](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/)
- [Which Python GUI library in 2026 — pythonguis.com](https://www.pythonguis.com/faq/which-python-gui-library/)
- [Building Desktop Apps in Python 2026 — thelinuxcode.com](https://thelinuxcode.com/building-desktop-applications-in-python-2026-from-gui-toolkit-choice-to-shipping-installers/)

### 3.2 SVN Integration Layer

| Option | Pros | Cons | Decision |
|---|---|---|---|
| **`svn` CLI subprocess** | Always matches installed SVN version; zero native deps | Parsing overhead; slower for bulk ops | **Primary** — reliable, version-safe |
| **`subvertpy`** (Python C bindings) | Faster for bulk operations | Requires libsvn-dev at build time; less maintained | **Optional accelerator** |
| **`pysvn`** (SWIG bindings) | Mature, supports transactions & hooks | Heavy C dependency; SourceForge-hosted | Rejected for MVP |

**Decision**: Use `subprocess` wrapping the `svn` / `svnadmin` / `svnlook` CLI tools as the primary integration. This avoids native compilation dependencies and always matches the user's installed Subversion version. `subvertpy` can be added later as an optional performance path.

*Sources*:
- [subvertpy on PyPI](https://pypi.org/project/subvertpy/)
- [pysvn — sourceforge.io](https://pysvn.sourceforge.io/)
- [svn (Python wrapper) — PyPI](https://pypi.org/project/svn/)

### 3.3 Credential Storage — **`keyring` library + Secret Service API**

The Python `keyring` library (MIT license) integrates with the Linux desktop's native secret storage (GNOME Keyring / KDE Wallet) via the freedesktop.org Secret Service D-Bus API. No plaintext credential files.

*Sources*:
- [keyring on PyPI](https://pypi.org/project/keyring/)
- [keyring documentation](https://keyring.readthedocs.io/en/latest/)

### 3.4 Packaging — **Flatpak (primary) + .deb (secondary)**

| Format | Pros | Cons |
|---|---|---|
| **Flatpak** | Distro-agnostic; sandboxed; auto-updates via Flathub | Larger bundle; sandbox may need portal permissions for SVN CLI |
| **.deb** | Native on Ubuntu/Debian (largest desktop base); small | Distro-specific; manual dependency management |
| AppImage | Single file; no install | No auto-update; security concerns; no sandboxing |
| Snap | Auto-update; sandboxed | Canonical-controlled store; slower startup |

**Decision**: Ship Flatpak as the universal package (with portal permissions for filesystem and SVN CLI access). Provide .deb for Debian/Ubuntu users who prefer native packages. AppImage rejected due to security concerns. **Each application (Client and Server) produces its own separate Flatpak and .deb package.** The build/bundle scripts generate both packages from the single workspace.

*Sources*:
- [Snap vs Flatpak vs AppImage 2026 — computingforgeeks.com](https://computingforgeeks.com/snap-vs-flatpak-vs-appimage/)
- [Flatpak packaging — linuxconfig.org](https://linuxconfig.org/how-to-create-a-flatpak-package)
- [Linux packaging for Python GUIs — pythonguis.com](https://www.pythonguis.com/faq/linux-packaging-prefered-formats/)

### 3.5 Project Structure — **Two Separate Applications, One Workspace**

| Aspect | Decision |
|---|---|
| Workspace layout | Single workspace with `svn_client/`, `svn_server/`, and `svn_shared/` top-level directories |
| Shared code | Common services (SvnCommandRunner, CredentialManager) live in `svn_shared/` and are imported by both apps |
| Packaging | Each app has its own `pyproject.toml`, Flatpak manifest, and debian/ directory |
| Build scripts | A top-level `Makefile` and `scripts/` orchestrate building both projects; each project also has its own Makefile |
| Installation | Users install `svn-client` and/or `svn-server-admin` independently; neither depends on the other at runtime |
| Shared lib distribution | `svn_shared` is bundled into each package at build time (vendored), not published as a separate PyPI package |

---

## 4. Functional Requirements — SVN Client UI

### 4.1 Working Copy Management
- **FR-C01**: Open/browse an existing working copy from the filesystem.
- **FR-C02**: Checkout a remote repository to a local path (svn checkout).
- **FR-C03**: Display working copy root info (URL, revision, UUID).

### 4.2 Status & Diff
- **FR-C10**: Show file status tree (modified, added, deleted, conflicted, unversioned).
- **FR-C11**: Inline diff viewer with syntax highlighting (side-by-side and unified).
- **FR-C12**: Diff against BASE, HEAD, or arbitrary revision.

### 4.3 Log & History
- **FR-C20**: Revision log with author, date, message, changed paths.
- **FR-C21**: Filter/search log by author, date range, path, message text.
- **FR-C22**: Show diff for any log entry.

### 4.4 Core Operations
- **FR-C30**: Update working copy (svn update) with progress feedback.
- **FR-C31**: Commit with multi-line message editor and file selection.
- **FR-C32**: Add / Remove files from version control.
- **FR-C33**: Revert changes (file-level and directory-level).

### 4.5 Branching & Tagging
- **FR-C40**: Switch working copy to a different branch/tag (svn switch).
- **FR-C41**: Create branch or tag via svn copy (with standard layout detection).
- **FR-C42**: Visual branch selector showing trunk/branches/tags structure.

### 4.6 Conflict Resolution
- **FR-C50**: Detect and list conflicted files.
- **FR-C51**: Three-way merge guidance (mine / theirs / base) with visual indicators.
- **FR-C52**: Mark resolved after manual edit.

### 4.7 Credential Handling
- **FR-C60**: Store/retrieve SVN credentials via OS keyring (Secret Service API).
- **FR-C61**: Prompt for credentials on auth failure; offer to save.
- **FR-C62**: Support SVN's built-in auth cache as fallback.

---

## 5. Functional Requirements — SVN Server Admin UI

### 5.1 Repository Management
- **FR-S01**: Create new repository (svnadmin create) with selectable backend (FSFS/FSX).
- **FR-S02**: List repositories in a configured root directory.
- **FR-S03**: Display repository info (UUID, HEAD revision, size).
- **FR-S04**: Delete repository (with confirmation and optional backup).

### 5.2 User & Access Control
- **FR-S10**: Edit `svnserve.conf` settings via form UI (anon-access, auth-access, realm).
- **FR-S11**: Manage `passwd` file entries (add/remove/edit users) — for svnserve auth.
- **FR-S12**: Edit `authz` file with visual path-based permission matrix.
- **FR-S13**: Guidance panel for Apache/mod_dav_svn and svnserve+SASL setups.

### 5.3 Hook Management
- **FR-S20**: List available hooks per repository (pre-commit, post-commit, pre-revprop-change, etc.).
- **FR-S21**: Template library with common hook scripts (commit-msg validation, email notification, CI trigger).
- **FR-S22**: Enable/disable hooks (rename .tmpl); edit hook content with syntax highlighting.
- **FR-S23**: Test hook execution with dry-run simulation.

### 5.4 Service Configuration
- **FR-S30**: Guidance for svnserve daemon setup (systemd unit file template).
- **FR-S31**: Guidance for Apache + mod_dav_svn configuration.
- **FR-S32**: Display active SVN service status (systemctl integration).

### 5.5 Backup & Export
- **FR-S40**: Run `svnadmin dump` with progress bar; save to file.
- **FR-S41**: Run `svnadmin load` from dump file.
- **FR-S42**: Run `svnadmin hotcopy` for live backup.
- **FR-S43**: Scheduled backup guidance (cron template generation).

---

## 6. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Status tree for 10,000-file working copy loads in < 3 seconds |
| NFR-02 | Performance | Log view fetches and renders 500 revisions in < 2 seconds |
| NFR-03 | Security | No plaintext credential storage; keyring or SVN auth cache only |
| NFR-04 | Security | Server admin operations require elevated privileges; warn user |
| NFR-05 | Usability | Keyboard shortcuts for all primary operations |
| NFR-06 | Usability | Dark/light theme support via Qt palette |
| NFR-07 | Packaging | Flatpak bundle < 150 MB installed per application |
| NFR-08 | Compatibility | Subversion 1.10+ CLI required; detect and warn on older versions |
| NFR-09 | Accessibility | Screen reader support via Qt Accessibility framework |
| NFR-10 | Integration | Must not replace or conflict with existing build/deploy scripts |
| NFR-11 | Independence | Client and Server apps install and run independently; neither requires the other |
| NFR-12 | Build | A single workspace build script produces both packages separately |

---

## 7. Assumptions

1. The workspace may contain existing build/deploy scripts; the applications will provide integration hooks (CLI entry points, exit codes) rather than replacing them.
2. SVN CLI tools (`svn`, `svnadmin`, `svnlook`, `svnserve`) are installed on the target system.
3. Python 3.10+ is available (required by PySide6).
4. For server admin features, the user has appropriate filesystem permissions on the repository root.
5. Both applications are developed in the same workspace but are built and packaged as separate, independent deliverables.
6. Shared code (`svn_shared/`) is vendored into each package at build time — there is no separate shared library package to install.

---

## 8. Out of Scope (MVP)

- Windows/macOS support (Linux-first; cross-platform is a future goal).
- SVN merge tracking visualization (complex; deferred to v2).
- Built-in text editor for conflict resolution (use external merge tool).
- Repository mirroring (svnsync) management.
- LDAP/Active Directory integration for access control.

---

## 9. Acceptance Criteria Summary

| Feature | Acceptance |
|---|---|
| Checkout | User can checkout a public SVN repo and see the file tree |
| Commit | User can stage files, write a message, and commit successfully |
| Diff | Side-by-side diff renders correctly for text files |
| Repo Create | Admin can create a new FSFS repo and see it listed |
| Access Control | Admin can add a user and set path permissions via authz editor |
| Hook Mgmt | Admin can enable a pre-commit hook from a template |
| Credentials | Credentials stored in keyring; not visible in any config file |

---

*Content was rephrased for compliance with licensing restrictions. All sources cited inline.*
