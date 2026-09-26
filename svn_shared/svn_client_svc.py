"""SVN Client service — wraps svn CLI for working copy operations.

All methods return structured data (dataclasses), not raw strings.
This module has no Qt imports and can be tested without a display server.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

from svn_shared.exceptions import SvnAuthError, SvnCommandError, SvnConflictError
from svn_shared.svn_command import CommandResult, run_sync

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StatusEntry:
    """A single file's version-control status."""

    path: str
    status: str  # "modified", "added", "deleted", "conflicted", "unversioned", etc.
    props_status: str = "none"
    revision: int | None = None


@dataclass
class LogEntry:
    """A single revision log entry."""

    revision: int
    author: str
    date: datetime
    message: str
    changed_paths: list[ChangedPath] = field(default_factory=list)


@dataclass
class ChangedPath:
    """A path changed in a revision."""

    path: str
    action: str  # "A", "M", "D", "R"


@dataclass
class WCInfo:
    """Working copy info."""

    path: str
    url: str
    relative_url: str
    repo_root_url: str
    repo_uuid: str
    revision: int
    node_kind: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(args: list[str], cwd: str | None = None) -> CommandResult:
    """Run an svn command and raise on auth errors."""
    result = run_sync(args, cwd=cwd)
    if not result.success:
        stderr_lower = result.stderr.lower()
        if "authorization failed" in stderr_lower or "authentication" in stderr_lower:
            raise SvnAuthError(
                command=" ".join(args),
                exit_code=result.exit_code,
                stderr=result.stderr,
            )
        raise SvnCommandError(
            command=" ".join(args),
            exit_code=result.exit_code,
            stderr=result.stderr,
        )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def checkout(
    url: str,
    path: str,
    revision: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> CommandResult:
    """Checkout a remote repository to a local path.

    Args:
        url: Repository URL (svn://, http://, https://, file://).
        path: Local filesystem path for the working copy.
        revision: Optional revision (e.g. "HEAD", "42").
        username: Optional SVN username.
        password: Optional SVN password.

    Returns:
        CommandResult from the checkout operation.
    """
    args = ["svn", "checkout", url, path, "--non-interactive"]
    if revision:
        args.extend(["-r", revision])
    if username:
        args.extend(["--username", username])
    if password:
        args.extend(["--password", password])
    return _run(args)


def update(path: str, revision: str | None = None) -> CommandResult:
    """Update a working copy.

    Args:
        path: Working copy path.
        revision: Optional target revision.

    Returns:
        CommandResult from the update operation.
    """
    args = ["svn", "update", "--non-interactive"]
    if revision:
        args.extend(["-r", revision])
    return _run(args, cwd=path)


def commit(
    path: str,
    message: str,
    files: list[str] | None = None,
) -> int:
    """Commit changes in a working copy.

    Args:
        path: Working copy root.
        message: Commit message.
        files: Optional list of specific files to commit.

    Returns:
        The committed revision number.

    Raises:
        SvnConflictError: If there are unresolved conflicts.
    """
    args = ["svn", "commit", "-m", message, "--non-interactive"]
    if files:
        args.extend(files)
    result = _run(args, cwd=path)

    # Parse revision from output like "Committed revision 42."
    for line in result.stdout.splitlines():
        if "Committed revision" in line:
            rev_str = line.strip().rstrip(".").split()[-1]
            return int(rev_str)
    return 0


def status(path: str) -> list[StatusEntry]:
    """Get working copy status.

    Args:
        path: Working copy path.

    Returns:
        List of StatusEntry objects.
    """
    result = _run(["svn", "status", "--xml"], cwd=path)
    entries: list[StatusEntry] = []

    root = ET.fromstring(result.stdout)
    for entry_el in root.iter("entry"):
        entry_path = entry_el.get("path", "")
        wc_status = entry_el.find("wc-status")
        if wc_status is not None:
            item_status = wc_status.get("item", "normal")
            props = wc_status.get("props", "none")
            rev_str = wc_status.get("revision")
            rev = int(rev_str) if rev_str else None
            entries.append(StatusEntry(
                path=entry_path,
                status=item_status,
                props_status=props,
                revision=rev,
            ))
    return entries


def diff(path: str, revision: str | None = None, file: str | None = None) -> str:
    """Get unified diff output.

    Args:
        path: Working copy path.
        revision: Optional revision to diff against (e.g. "BASE", "HEAD", "42").
        file: Optional specific file to diff.

    Returns:
        Unified diff string.
    """
    args = ["svn", "diff"]
    if revision:
        args.extend(["-r", revision])
    if file:
        args.append(file)
    result = _run(args, cwd=path)
    return result.stdout


def log(
    path: str,
    limit: int = 100,
    revision_range: str | None = None,
) -> list[LogEntry]:
    """Get revision log.

    Args:
        path: Working copy or URL path.
        limit: Maximum number of log entries.
        revision_range: Optional revision range (e.g. "10:HEAD").

    Returns:
        List of LogEntry objects, newest first.
    """
    # Without an explicit -r, `svn log` pegs itself to the working copy's own
    # locally-recorded BASE revision for `path` -- which committing files
    # inside it does NOT advance (only the committed items themselves get
    # bumped; the containing directory's own revision stays frozen until an
    # explicit `svn update`). That made the log view silently miss the most
    # recent commit(s) until the user updated first. Default to HEAD so the
    # log always reflects the true repository state.
    args = ["svn", "log", "--xml", "-v", "-l", str(limit), "-r", revision_range or "HEAD:1"]
    result = _run(args, cwd=path)

    entries: list[LogEntry] = []
    root = ET.fromstring(result.stdout)
    for logentry in root.iter("logentry"):
        rev = int(logentry.get("revision", "0"))
        author_el = logentry.find("author")
        date_el = logentry.find("date")
        msg_el = logentry.find("msg")

        author = author_el.text if author_el is not None and author_el.text else ""
        date_str = date_el.text if date_el is not None and date_el.text else ""
        message = msg_el.text if msg_el is not None and msg_el.text else ""

        # Parse ISO date from SVN (e.g. "2026-04-30T12:00:00.000000Z")
        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            date = datetime.min

        changed: list[ChangedPath] = []
        paths_el = logentry.find("paths")
        if paths_el is not None:
            for path_el in paths_el.iter("path"):
                changed.append(ChangedPath(
                    path=path_el.text or "",
                    action=path_el.get("action", ""),
                ))

        entries.append(LogEntry(
            revision=rev,
            author=author,
            date=date,
            message=message,
            changed_paths=changed,
        ))
    return entries


def add(paths: list[str], cwd: str | None = None) -> CommandResult:
    """Add files to version control.

    Args:
        paths: List of file paths to add.
        cwd: Working copy root.
    """
    return _run(["svn", "add"] + paths, cwd=cwd)


def remove(paths: list[str], cwd: str | None = None) -> CommandResult:
    """Remove files from version control.

    Args:
        paths: List of file paths to remove.
        cwd: Working copy root.
    """
    return _run(["svn", "remove"] + paths, cwd=cwd)


def revert(paths: list[str], recursive: bool = False, cwd: str | None = None) -> CommandResult:
    """Revert local changes.

    Args:
        paths: Paths to revert.
        recursive: If True, revert recursively.
        cwd: Working copy root.
    """
    args = ["svn", "revert"]
    if recursive:
        args.append("-R")
    args.extend(paths)
    return _run(args, cwd=cwd)


def switch(path: str, url: str) -> CommandResult:
    """Switch working copy to a different branch/tag.

    Args:
        path: Working copy path.
        url: Target branch/tag URL.
    """
    return _run(["svn", "switch", url, "--non-interactive"], cwd=path)


def copy(src_url: str, dst_url: str, message: str) -> CommandResult:
    """Server-side copy (branch/tag creation).

    Args:
        src_url: Source URL.
        dst_url: Destination URL.
        message: Commit message for the copy.
    """
    return _run(["svn", "copy", src_url, dst_url, "-m", message, "--non-interactive"])


def info(path: str) -> WCInfo:
    """Get working copy info.

    Args:
        path: Working copy path.

    Returns:
        WCInfo dataclass with working copy metadata.
    """
    result = _run(["svn", "info", "--xml"], cwd=path)
    root = ET.fromstring(result.stdout)
    entry = root.find("entry")
    if entry is None:
        raise SvnCommandError(
            command="svn info --xml",
            exit_code=0,
            stderr="No <entry> element in svn info output",
        )

    url_el = entry.find("url")
    relurl_el = entry.find("relative-url")
    repo_el = entry.find("repository")
    repo_root = repo_el.find("root") if repo_el is not None else None
    repo_uuid = repo_el.find("uuid") if repo_el is not None else None

    return WCInfo(
        path=entry.get("path", ""),
        url=url_el.text if url_el is not None and url_el.text else "",
        relative_url=relurl_el.text if relurl_el is not None and relurl_el.text else "",
        repo_root_url=repo_root.text if repo_root is not None and repo_root.text else "",
        repo_uuid=repo_uuid.text if repo_uuid is not None and repo_uuid.text else "",
        revision=int(entry.get("revision", "0")),
        node_kind=entry.get("kind", ""),
    )


def resolve(path: str, file: str) -> CommandResult:
    """Mark a conflicted file as resolved.

    Args:
        path: Working copy root.
        file: Conflicted file path.
    """
    return _run(["svn", "resolve", "--accept", "working", file], cwd=path)
