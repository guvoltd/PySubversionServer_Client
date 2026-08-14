# SVN Desktop Suite — Project Hub (kiro.md)

> **Version**: 1.1.0 | **Last Updated**: 2026-04-30
> **Status**: 📋 MVP Planning Complete (Revised) — Ready for Implementation

---

## 1. Project Summary

The **SVN Desktop Suite** consists of two **separate** Linux desktop applications developed in a single workspace:

1. **SVN Client** (`svn_client/`) — a developer-facing GUI for Subversion working copy operations (checkout, commit, diff, log, branch, conflict resolution).
2. **SVN Server Admin** (`svn_server/`) — an admin-facing GUI for managing SVN repositories, access control, hooks, service configuration, and backups.

Both applications share a common service library (`svn_shared/`) that is vendored into each package at build time. They are built, packaged, and distributed as **independent installable packages** — users install one or both depending on their role. The workspace-level build scripts generate both packages separately.

---

## 2. Chosen Stack & Rationale

| Component | Choice | Rationale |
|---|---|---|
| **GUI Framework** | PySide6 (Qt 6) | LGPL license allows open-source and commercial distribution; richest widget set for tree views, diffs, dockable panels; official Qt Company Python bindings; strong Linux desktop integration |
| **Language** | Python 3.10+ | Type hints, dataclasses, async subprocess; large ecosystem; matches PySide6 requirement |
| **SVN Integration** | subprocess (svn/svnadmin CLI) | Always matches installed SVN version; no native compilation deps; reliable and well-documented |
| **Credential Storage** | `keyring` library (MIT) | Integrates with GNOME Keyring / KDE Wallet via Secret Service D-Bus API; no plaintext storage |
| **Primary Packaging** | Flatpak | Distro-agnostic; sandboxed; auto-updates; largest cross-distro reach |
| **Secondary Packaging** | .deb | Native on Ubuntu/Debian (largest desktop Linux base); smaller bundle |
| **Testing** | pytest + pytest-qt | Standard Python testing; Qt widget testing support |
| **Linting/Types** | ruff + mypy | Fast linting; strict type checking on service layer |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    WORKSPACE ROOT                        │
├──────────────────┬──────────────────┬───────────────────┤
│  svn_client/     │  svn_server/     │  svn_shared/      │
│  (App 1 — .deb/  │  (App 2 — .deb/  │  (Common library  │
│   flatpak)       │   flatpak)       │   vendored into   │
│                  │                  │   both apps)       │
│  ClientMainWin   │  ServerMainWin   │  SvnCommandRunner  │
│  StatusTree      │  RepoManager     │  SvnClientSvc      │
│  DiffViewer      │  AccessEditor    │  SvnAdminSvc       │
│  LogViewer       │  HookManager     │  CredentialMgr     │
│  CommitDialog    │  ServicePanel    │  ConfigParser      │
│  BranchDialog    │  BackupPanel     │  Shared Widgets    │
│  ConflictPanel   │                  │                    │
└──────────────────┴──────────────────┴───────────────────┘
```

Key architectural principles:
- **Two separate applications** — independent install, independent release cycles.
- **Shared library vendored at build time** — code reuse without runtime coupling.
- **Service layer has minimal Qt imports** — testable without display server.
- **Async command execution** — all SVN CLI calls run in QThread workers.
- **Atomic config writes** — backup before modify for all SVN config files.

---

## 4. File Index

### Documentation (this system)

| File | Purpose | Owner |
|---|---|---|
| `docs/kiro/kiro.md` | Project hub, decisions, status, handoff | All agents |
| `docs/kiro/requirements.md` | Product requirements & tech decisions | Requirements Agent |
| `docs/kiro/design.md` | Architecture, modules, wireframes | Design Agent |
| `docs/kiro/code_tasks.md` | Implementation task breakdown & tracking | Code Agent |
| `docs/kiro/testing_steps.md` | Test plan, cases, fixtures, CI pipeline | Test Agent |
| `docs/kiro/aiAgents/agent_req.md` | Requirements Agent role & rules | Requirements Agent |
| `docs/kiro/aiAgents/agent_design.md` | Design Agent role & rules | Design Agent |
| `docs/kiro/aiAgents/agent_code.md` | Code Agent role & rules | Code Agent |
| `docs/kiro/aiAgents/agent_test.md` | Test Agent role & rules | Test Agent |

### Source Code (planned)

| Path | Purpose |
|---|---|
| `svn_shared/` | Shared service library (vendored into both apps) |
| `svn_shared/widgets/` | Reusable custom Qt widgets |
| `svn_shared/resources/` | Shared icons, styles |
| `svn_shared/tests/` | Shared library unit tests |
| `svn_client/` | SVN Client application |
| `svn_client/tests/` | Client UI tests |
| `svn_server/` | SVN Server Admin application |
| `svn_server/tests/` | Server UI tests |

### Build & Packaging (planned)

| Path | Purpose |
|---|---|
| `Makefile` | Top-level orchestrator (build-all, test-all, package-all) |
| `svn_client/pyproject.toml` | Client PEP 621 project metadata |
| `svn_client/Makefile` | Client-specific build targets |
| `svn_client/flatpak/` | Client Flatpak manifest |
| `svn_client/debian/` | Client .deb packaging |
| `svn_server/pyproject.toml` | Server PEP 621 project metadata |
| `svn_server/Makefile` | Server-specific build targets |
| `svn_server/flatpak/` | Server Flatpak manifest |
| `svn_server/debian/` | Server .deb packaging |
| `scripts/` | Workspace-level build/deploy helper scripts |

---

## 5. Decision Log

| Date | Decision | Rationale | Agent |
|---|---|---|---|
| 2026-04-30 | PySide6 over PyQt6 | LGPL license; no commercial license needed for distribution | Requirements |
| 2026-04-30 | subprocess over subvertpy | No native deps; matches installed SVN version; simpler build | Requirements |
| 2026-04-30 | keyring for credentials | OS-native secret storage; MIT license; well-maintained | Requirements |
| 2026-04-30 | Flatpak primary packaging | Distro-agnostic; sandboxed; Flathub distribution | Requirements |
| 2026-04-30 | ~~Single app with tabs~~ → **Two separate apps** | Different user roles install different tools; independent release cycles; shared lib vendored | Requirements (revised) |
| 2026-04-30 | Service layer with minimal Qt | Enables unit testing without display; potential CLI reuse | Design |
| 2026-04-30 | 6-phase implementation | Clear dependency chain; parallelizable where possible | Code |
| 2026-04-30 | 80% coverage target on svn_shared/ | Balances thoroughness with MVP velocity | Test |
| 2026-04-30 | Shared library vendored, not published | Avoids PyPI dependency; simpler build; each app is self-contained | Design (revised) |

---

## 6. Current Status

### Phase Status

| Phase | Name | Status |
|---|---|---|
| 0 | Project Scaffolding | ✅ Complete |
| 1 | Backend / Service Layer | ✅ Complete |
| 2 | Qt UI Shell | ✅ Complete (both app shells) |
| 3 | SVN Client UI | ⬜ Not started |
| 4 | SVN Server Admin UI | ⬜ Not started |
| 5 | Packaging & Distribution | ⬜ Not started |
| 6 | Polish & Integration | ⬜ Not started |

### Agent Status

| Agent | Last Active | Current State |
|---|---|---|
| Requirements | 2026-04-30 | ✅ MVP requirements complete |
| Design | 2026-04-30 | ✅ MVP design complete |
| Code | 2026-04-30 | ✅ Task breakdown complete; ready to implement |
| Test | 2026-04-30 | ✅ Test plan complete; ready to execute alongside dev |

---

## 7. Next Actions

1. **Code Agent**: Begin Phase 3 — implement `StatusTree` widget (T-300), then `DiffViewer` (T-301).
2. **Code Agent**: Begin Phase 4 in parallel — implement `RepoManager` (T-400).
3. **Test Agent**: Write UI smoke tests for the new widgets as they are implemented.
4. **Requirements Agent**: No action needed unless stakeholder feedback arrives.
5. **Design Agent**: No action needed unless implementation reveals design gaps.

---

## 8. Session Handoff

### Session 1 — 2026-04-30 (Initial Planning)

**What was done:**
- Requirements Agent performed web research on GUI frameworks, SVN integration libraries, credential storage, and Linux packaging formats.
- Requirements Agent produced complete `requirements.md` with technology decisions, functional requirements (FR-C01 through FR-C62 for client, FR-S01 through FR-S43 for server), non-functional requirements, and acceptance criteria.
- Design Agent produced complete `design.md` with architecture diagram, module decomposition, UI wireframes, data flow diagrams, integration points, and security design.
- Code Agent produced complete `code_tasks.md` with 6 phases, 25+ tasks, dependency graph, and status tracking.
- Test Agent produced complete `testing_steps.md` with unit tests, integration tests, UI smoke tests, manual checklists, CI pipeline, and test fixtures.
- All four agent definition files created with roles, responsibilities, workflow rules, handoff protocols, and session persistence instructions.

**Key decisions made:**
- PySide6 (LGPL) chosen over PyQt6 (GPL) for licensing flexibility.
- subprocess-based SVN integration chosen for reliability and zero native deps.
- Flatpak chosen as primary packaging format for cross-distro reach.

**What to do next session:**
- Start implementation with Phase 0 (project scaffolding).
- The Code Agent should create `pyproject.toml` and the package skeleton first.
- The Test Agent should set up the test infrastructure (pytest config, fixtures) in parallel.

**Open questions:**
- None blocking. The workspace was empty, so all build/deploy integration points are defined as extensible hooks rather than hard-coded paths.

---

### Session 2 — 2026-04-30 (Architecture Correction: Separate Projects)

**What was done:**
- **Requirements Agent** revised `requirements.md` (v1.0 → v1.1):
  - Product vision rewritten: two separate applications, not a single tabbed app.
  - Added section 3.5 (Project Structure) documenting the workspace layout with `svn_client/`, `svn_server/`, `svn_shared/`.
  - Added NFR-11 (independence) and NFR-12 (build produces both packages separately).
  - Updated assumptions to reflect separate packaging and vendored shared library.
- **Design Agent** revised `design.md` (v1.0 → v1.1):
  - Architecture diagram redrawn for two independent apps + shared library.
  - Package structure completely reorganized: `svn_client/`, `svn_server/`, `svn_shared/` at workspace root.
  - Design decision 3.1 changed from "Single Application, Tabbed Interface" to "Two Separate Applications, Shared Library".
  - Each app gets its own `QMainWindow`, `pyproject.toml`, `Makefile`, Flatpak manifest, and debian/ directory.
  - Wireframes updated: removed tab bar; each app has its own full window layout.
  - Settings split into per-app `QSettings` namespaces.
  - Integration points updated with per-project and top-level Makefile targets.
- **Code Agent** revised `code_tasks.md` (v1.0 → v1.1):
  - Phase 0 expanded: T-000 (shared lib), T-001 (client project), T-002 (server project), T-003 (top-level Makefile), T-004 (resources).
  - Phase 1 file paths updated to `svn_shared/`.
  - Phase 2 split into T-200 (client shell), T-201 (server shell), T-202 (settings per app).
  - Phase 3/4 file paths updated to `svn_client/` and `svn_server/`.
  - Phase 5 expanded: separate Flatpak + .deb tasks for each app (T-500 through T-504).
  - Phase 6 added T-603 (shared library vendoring).
  - Dependency graph updated for two parallel packaging streams.
- **Test Agent** revised `testing_steps.md` (v1.0 → v1.1):
  - Added section 1.4 (Test Organization) documenting three test locations.
  - Coverage target updated to reference `svn_shared/`.
  - UI smoke tests split: QT-300 for client window, QT-302-00 for server window.
  - Makefile targets updated for multi-package test runs.
  - Manual usability checklist updated with independence verification tests.
- **kiro.md** updated with revised architecture, file index, decision log, and this handoff entry.

**Key decision changed:**
- ~~Single tabbed application~~ → **Two separate applications** with shared library vendored at build time. Rationale: different user roles, independent release cycles, separate install footprints.

**What to do next session:**
- Start implementation with Phase 0 — create the three-directory workspace structure.
- Code Agent should create `svn_shared/` first (T-000), then both project skeletons (T-001, T-002) in parallel.
- Top-level Makefile (T-003) can be done alongside project skeletons.

**Open questions:**
- None blocking.

---

### Session 3 — 2026-04-30 (Implementation: Phases 0, 1, 2)

**What was done:**
- Verified environment: Python 3.12.3, pip 24.0, SVN 1.14.3, svnadmin available.
- **Phase 0 — Project Scaffolding (all 5 tasks ✅)**:
  - Created `svn_shared/` with `__init__.py`, `exceptions.py`, `widgets/`, `resources/styles/`, `tests/`.
  - Created `svn_client/` with `__init__.py`, `__main__.py`, `app.py`, `pyproject.toml`, `tests/`, `resources/`.
  - Created `svn_server/` with `__init__.py`, `__main__.py`, `app.py`, `pyproject.toml`, `tests/`, `resources/`.
  - Created top-level `Makefile` with 15 targets (build-all, test-all, lint-all, etc.).
  - Created `scripts/` with 6 shell scripts (build-all, package-*, run-dev).
  - Created QSS theme files (light + dark) and 3 hook template scripts.
- **Phase 1 — Backend Service Layer (all 6 tasks ✅)**:
  - `svn_shared/svn_command.py` — async subprocess runner with validation, timeout, cancellation.
  - `svn_shared/svn_client_svc.py` — full client service (checkout, update, commit, status, diff, log, add, remove, revert, switch, copy, info, resolve).
  - `svn_shared/svn_admin_svc.py` — full admin service (create, list, info, delete, dump, load, hotcopy, verify).
  - `svn_shared/config_parser.py` — INI parser for svnserve.conf, authz, passwd with comment preservation and backup.
  - `svn_shared/credential_mgr.py` — keyring integration with graceful fallback.
  - `svn_shared/hook_templates.py` — built-in templates + install/enable/disable/list.
  - `svn_shared/widgets/` — syntax_highlighter.py (diff + shell), progress_overlay.py, search_bar.py.
- **Phase 2 — Qt UI Shells (both apps ✅)**:
  - `svn_client/app.py` — ClientMainWindow with menu bar, toolbar, splitter layout, status bar, theme loading, geometry persistence.
  - `svn_server/app.py` — ServerMainWindow with menu bar, toolbar, repo list + detail tabs, status bar, theme loading.
- **Unit Tests — 44 tests, all passing**:
  - `test_svn_command.py` — 12 tests (validation, sync, async, cancel, timeout, injection prevention).
  - `test_svn_client_svc.py` — 6 tests (status/log/commit/diff/info XML parsing, auth error).
  - `test_svn_admin_svc.py` — 9 tests (create, list, info, delete with/without backup, verify).
  - `test_config_parser.py` — 7 tests (parse/write round-trip for all 3 config files).
  - `test_credential_mgr.py` — 7 tests (store/retrieve/delete with mock keyring, unavailable fallback).

**What to do next session:**
- Phase 3: Build the client UI widgets (StatusTree, DiffViewer, LogViewer, dialogs).
- Phase 4: Build the server admin UI widgets (RepoManager, AccessEditor, HookManager, BackupPanel).
- Phases 3 and 4 can be done in parallel.

**Open questions:**
- None blocking.

---

*To add a new handoff entry: append a new `### Session N` section below the last one with the same structure.*
