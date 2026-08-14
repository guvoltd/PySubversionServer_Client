# Testing Steps — SVN Desktop Suite (Linux)

> **Agent**: Test Agent | **Version**: 1.1.0 | **Date**: 2026-04-30
> **Status**: MVP Test Plan (Revised — Two Separate Apps) — Ready for Execution Alongside Development

---

## 1. Test Strategy

### 1.1 Test Pyramid

```
         ┌──────────┐
         │  Manual   │  ← Exploratory, accessibility, UX
         │  E2E      │
        ┌┴──────────┴┐
        │ Integration │  ← Real SVN repos (temp dirs)
       ┌┴────────────┴┐
       │   Unit Tests  │  ← Mocked subprocess, fast
       └──────────────┘
```

### 1.2 Tooling

| Tool | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-qt` | Qt widget testing (simulated events, signal assertions) |
| `pytest-cov` | Coverage reporting |
| `unittest.mock` | Mocking subprocess, keyring, filesystem |
| `tmp_path` fixture | Temporary directories for SVN repo fixtures |
| `ruff` | Linting (run as pre-test gate) |
| `mypy` | Type checking (run as pre-test gate) |

### 1.3 Coverage Target

- **MVP target**: 80% line coverage on `svn_shared/` package (shared services).
- **UI coverage**: Smoke tests for widget creation and signal wiring in both `svn_client/` and `svn_server/`; not pixel-level.

### 1.4 Test Organization

Tests are split across three locations:
- `svn_shared/tests/` — unit tests for shared services (no Qt, no SVN CLI needed).
- `svn_client/tests/` — client UI smoke tests + client integration tests.
- `svn_server/tests/` — server UI smoke tests + server integration tests.

---

## 2. Unit Tests — Service Layer (in `svn_shared/tests/`)

### UT-100: SvnCommandRunner

| ID | Test Case | Input | Expected |
|---|---|---|---|
| UT-100-01 | Successful command | `["svn", "info"]` | exit_code=0, stdout captured |
| UT-100-02 | Failed command | `["svn", "checkout", "bad://url"]` | exit_code≠0, stderr captured |
| UT-100-03 | Timeout | Long-running mock | TimeoutError raised after threshold |
| UT-100-04 | Cancellation | Cancel during run | Process terminated, no crash |
| UT-100-05 | Shell injection prevention | Args with `;rm -rf /` | Args passed as list, no shell expansion |
| UT-100-06 | Empty args | `[]` | ValueError raised |

### UT-101: SvnClientService

| ID | Test Case | Mock Setup | Expected |
|---|---|---|---|
| UT-101-01 | status() parsing | Mock `svn status --xml` output | List of (path, status) tuples |
| UT-101-02 | log() parsing | Mock `svn log --xml` output | List of LogEntry dataclasses |
| UT-101-03 | diff() output | Mock `svn diff` output | Raw diff string returned |
| UT-101-04 | commit() success | Mock exit_code=0 | Returns committed revision number |
| UT-101-05 | commit() auth failure | Mock stderr with auth error | Raises SvnAuthError |
| UT-101-06 | checkout() progress | Mock incremental stdout | Progress callback invoked per line |
| UT-101-07 | info() parsing | Mock `svn info --xml` output | Dict with URL, revision, UUID |
| UT-101-08 | add() multiple files | List of 3 paths | Single svn add call with all paths |
| UT-101-09 | revert() directory | Directory path | `svn revert -R` called |
| UT-101-10 | switch() | URL + path | `svn switch` called with correct args |

### UT-102: SvnAdminService

| ID | Test Case | Mock Setup | Expected |
|---|---|---|---|
| UT-102-01 | create_repo() | Mock svnadmin create | Directory structure verified |
| UT-102-02 | create_repo() with standard layout | Mock svnadmin + svn mkdir | trunk/branches/tags created |
| UT-102-03 | list_repos() | Temp dir with 2 repo dirs | Returns 2 repo info dicts |
| UT-102-04 | repo_info() | Mock svnlook info | Returns UUID, HEAD rev |
| UT-102-05 | delete_repo() with backup | Mock hotcopy + rmtree | Backup created before delete |
| UT-102-06 | dump() | Mock svnadmin dump | Output file path returned |
| UT-102-07 | verify() | Mock svnadmin verify | Returns True on success |

### UT-103: ConfigParser

| ID | Test Case | Input | Expected |
|---|---|---|---|
| UT-103-01 | Parse svnserve.conf | Sample conf content | SvnserveConfig dataclass populated |
| UT-103-02 | Write svnserve.conf | Modified SvnserveConfig | File written with comments preserved |
| UT-103-03 | Parse authz | Sample authz content | List of AuthzRule objects |
| UT-103-04 | Write authz | Modified rules | File written, permissions correct |
| UT-103-05 | Parse passwd | Sample passwd content | List of PasswdEntry objects |
| UT-103-06 | Round-trip preservation | Parse → modify → write → parse | Comments and ordering preserved |
| UT-103-07 | Backup on write | Any write operation | `.bak` file created |
| UT-103-08 | Invalid file handling | Malformed conf | Raises ConfigParseError with line number |

### UT-104: CredentialManager

| ID | Test Case | Mock Setup | Expected |
|---|---|---|---|
| UT-104-01 | store() + retrieve() | Mock keyring backend | Credentials round-trip correctly |
| UT-104-02 | retrieve() missing | Empty keyring | Returns None |
| UT-104-03 | delete() | Stored credential | Credential removed |
| UT-104-04 | keyring unavailable | Mock NoKeyringError | Warning logged, graceful failure |

### UT-105: HookTemplateManager

| ID | Test Case | Input | Expected |
|---|---|---|---|
| UT-105-01 | list_templates() | Built-in templates dir | Returns 3+ templates |
| UT-105-02 | install_hook() | Template content + repo path | File written with +x permission |
| UT-105-03 | list_hooks() | Repo with 2 hooks | Returns names + enabled status |
| UT-105-04 | enable/disable toggle | Existing hook | File renamed (.tmpl ↔ no extension) |

---

## 3. Integration Tests

These tests use real SVN repositories created in temporary directories.

### IT-200: End-to-End Client Workflow

**Prerequisite**: `svn` and `svnadmin` available on PATH.

| ID | Test Case | Steps | Expected |
|---|---|---|---|
| IT-200-01 | Full lifecycle | 1. svnadmin create temp repo 2. checkout 3. add file 4. commit 5. modify 6. status 7. diff 8. log 9. update | All operations succeed; log shows 1 revision |
| IT-200-02 | Branch + switch | 1. Create repo with standard layout 2. Checkout trunk 3. Create branch 4. Switch to branch 5. Commit on branch | Working copy on branch; log shows branch commit |
| IT-200-03 | Conflict detection | 1. Two checkouts of same repo 2. Modify same file in both 3. Commit first 4. Update second | Conflict detected; status shows 'C' |

### IT-201: End-to-End Admin Workflow

| ID | Test Case | Steps | Expected |
|---|---|---|---|
| IT-201-01 | Repo management | 1. Create repo 2. List repos 3. Get info 4. Delete | All operations succeed; list empty after delete |
| IT-201-02 | Config editing | 1. Create repo 2. Parse svnserve.conf 3. Modify 4. Write 5. Re-parse | Modified values persisted correctly |
| IT-201-03 | Hook management | 1. Create repo 2. Install hook 3. List hooks 4. Disable 5. Enable | Hook state toggles correctly |
| IT-201-04 | Dump and load | 1. Create repo 2. Add content 3. Dump 4. Create new repo 5. Load | New repo has same content and history |

---

## 4. UI Smoke Tests (pytest-qt)

These verify widgets instantiate and basic interactions work. They do NOT test visual appearance. Client tests live in `svn_client/tests/`, server tests in `svn_server/tests/`.

### QT-300: SVN Client Main Window

| ID | Test Case | Expected |
|---|---|---|
| QT-300-01 | Window creation | ClientMainWindow instantiates without error |
| QT-300-02 | Menu bar | All menus present and have expected actions |
| QT-300-03 | Toolbar | All toolbar actions present |
| QT-300-04 | Theme toggle | Switching theme does not crash |

### QT-301: Client Widgets

| ID | Test Case | Expected |
|---|---|---|
| QT-301-01 | StatusTree creation | Widget renders with empty model |
| QT-301-02 | StatusTree population | Feeding mock data shows correct rows |
| QT-301-03 | DiffViewer modes | Toggle between side-by-side and unified |
| QT-301-04 | LogViewer population | Mock log entries render in table |
| QT-301-05 | CommitDialog validation | Commit button disabled when message empty |
| QT-301-06 | CheckoutDialog URL validation | Invalid URL shows error indicator |

### QT-302: SVN Server Admin Main Window & Widgets

| ID | Test Case | Expected |
|---|---|---|
| QT-302-00 | Window creation | ServerMainWindow instantiates without error |
| QT-302-01 | RepoManager creation | Widget renders with empty list |
| QT-302-02 | AccessEditor tabs | All 3 sub-tabs accessible |
| QT-302-03 | HookManager template list | Templates populate dropdown |
| QT-302-04 | BackupPanel controls | All buttons present and labeled |

---

## 5. Manual Test Checklist

### MT-500: Accessibility

- [ ] All interactive elements reachable via Tab key.
- [ ] Screen reader announces widget labels (test with Orca).
- [ ] Diff viewer colors have sufficient contrast (WCAG AA).
- [ ] Dialogs are keyboard-dismissable (Escape key).
- [ ] Focus indicators visible on all interactive elements.

> **Note**: Full WCAG compliance validation requires manual testing with assistive technologies and expert accessibility review.

### MT-501: Usability

- [ ] **Client**: Checkout a public SVN repo (e.g., Apache project) — completes without error.
- [ ] **Client**: Commit cycle: modify file → see status → diff → commit → verify in log.
- [ ] **Server**: Create repository → add user → set permissions → verify access.
- [ ] **Server**: Install hook from template → verify it appears in hook list.
- [ ] **Server**: Dump repository → load into new repo → verify content matches.
- [ ] **Both**: Switch between light and dark themes — all text readable.
- [ ] **Both**: Resize window to minimum size — no widget overlap or truncation.
- [ ] **Independence**: Install only the client package — verify it works without server package.
- [ ] **Independence**: Install only the server package — verify it works without client package.

### MT-502: Error Handling

- [ ] Attempt checkout with invalid URL → clear error message.
- [ ] Attempt commit with no changes → informative message.
- [ ] Attempt server admin without permissions → privilege warning.
- [ ] Kill SVN process mid-operation → app recovers gracefully.
- [ ] Disconnect network during remote operation → timeout + error message.

---

## 6. CI Pipeline Stages

```
┌─────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────┐
│  Lint   │───→│  Type    │───→│  Unit Tests │───→│Integration│
│  (ruff) │    │  (mypy)  │    │  (pytest)   │    │  Tests   │
└─────────┘    └──────────┘    └─────────────┘    └──────────┘
                                      │
                                      ▼
                               ┌─────────────┐
                               │  Coverage   │
                               │  Report     │
                               └─────────────┘
```

### Makefile Targets (top-level)

```makefile
test-all:           ## Run all tests across all packages
    pytest svn_shared/tests/ svn_client/tests/ svn_server/tests/ -v --tb=short

test-shared:        ## Run shared library unit tests
    pytest svn_shared/tests/ -v --tb=short

test-client:        ## Run client tests (unit + UI smoke)
    pytest svn_client/tests/ -v --tb=short

test-server:        ## Run server tests (unit + UI smoke)
    pytest svn_server/tests/ -v --tb=short

test-unit:          ## Run unit tests only (all packages)
    pytest svn_shared/tests/ svn_client/tests/ svn_server/tests/ -v --tb=short -m "not integration"

test-integration:   ## Run integration tests (requires svn)
    pytest svn_shared/tests/ svn_client/tests/ svn_server/tests/ -v --tb=short -m integration

test-ui:            ## Run UI smoke tests (requires display or xvfb)
    pytest svn_client/tests/ svn_server/tests/ -v --tb=short -m ui

coverage:           ## Run tests with coverage
    pytest svn_shared/tests/ --cov=svn_shared --cov-report=html --cov-report=term

lint-all:           ## Run linter on all packages
    ruff check svn_shared/ svn_client/ svn_server/

typecheck:          ## Run type checker
    mypy svn_shared/ svn_client/ svn_server/
```

---

## 7. Test Data & Fixtures

### Fixture: Temporary SVN Repository

```python
@pytest.fixture
def svn_repo(tmp_path):
    """Create a temporary SVN repository for testing."""
    repo_path = tmp_path / "test-repo"
    subprocess.run(["svnadmin", "create", str(repo_path)], check=True)
    return repo_path

@pytest.fixture
def svn_wc(svn_repo, tmp_path):
    """Create a working copy from the temp repo."""
    wc_path = tmp_path / "test-wc"
    repo_url = f"file://{svn_repo}"
    subprocess.run(["svn", "checkout", repo_url, str(wc_path)], check=True)
    return wc_path
```

### Fixture: Mock SVN Output

```python
MOCK_SVN_STATUS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<status>
  <target path=".">
    <entry path="modified.py"><wc-status item="modified" props="none" revision="5"/></entry>
    <entry path="added.py"><wc-status item="added" props="none"/></entry>
    <entry path="deleted.py"><wc-status item="deleted" props="none" revision="3"/></entry>
  </target>
</status>"""
```
