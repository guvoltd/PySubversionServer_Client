"""SVN Admin service — wraps svnadmin/svnlook CLI for repository management.

This module has no Qt imports and can be tested without a display server.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
import subprocess

from svn_shared.exceptions import SvnCommandError, SvnNotFoundError
from svn_shared.svn_command import CommandResult, run_sync

logger = logging.getLogger(__name__)


@dataclass
class RepoInfo:
    """Repository metadata."""

    name: str
    path: str
    uuid: str
    head_revision: int
    fs_type: str
    size_bytes: int | None = None


def _run(args: list[str], cwd: str | None = None) -> CommandResult:
    """Run a command and raise on failure."""
    result = run_sync(args, cwd=cwd)
    if not result.success:
        raise SvnCommandError(
            command=" ".join(args),
            exit_code=result.exit_code,
            stderr=result.stderr,
        )
    return result


def create_repo(
    root: str,
    name: str,
    fs_type: str = "fsfs",
    standard_layout: bool = False,
) -> str:
    """Create a new SVN repository.

    Args:
        root: Parent directory for repositories.
        name: Repository name (becomes a subdirectory).
        fs_type: Filesystem backend — "fsfs" or "fsx".
        standard_layout: If True, create trunk/branches/tags structure.

    Returns:
        Full path to the created repository.
    """
    repo_path = os.path.join(root, name)
    _run(["svnadmin", "create", "--fs-type", fs_type, repo_path])
    logger.info("Created repository: %s", repo_path)

    if standard_layout:
        repo_url = f"file://{os.path.abspath(repo_path)}"
        dirs = [
            f"{repo_url}/trunk",
            f"{repo_url}/branches",
            f"{repo_url}/tags",
        ]
        _run(["svn", "mkdir"] + dirs + ["-m", "Create standard layout", "--non-interactive"])
        logger.info("Created standard layout in %s", repo_path)

    return repo_path


def list_repos(root: str) -> list[RepoInfo]:
    """List all SVN repositories under a root directory.

    Args:
        root: Parent directory containing repositories.

    Returns:
        List of RepoInfo for each valid repository found.
    """
    if not os.path.isdir(root):
        raise SvnNotFoundError(f"Repository root not found: {root}")

    repos: list[RepoInfo] = []
    for entry in sorted(os.listdir(root)):
        candidate = os.path.join(root, entry)
        # A valid SVN repo has a db/ and format file.
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "format")):
            try:
                info = repo_info(candidate)
                repos.append(info)
            except (SvnCommandError, OSError) as exc:
                logger.warning("Skipping %s: %s", candidate, exc)
    return repos


def repo_info(path: str) -> RepoInfo:
    """Get metadata for a single repository.

    Args:
        path: Full path to the repository.

    Returns:
        RepoInfo dataclass.
    """
    if not os.path.isdir(path):
        raise SvnNotFoundError(f"Repository not found: {path}")

    # UUID
    result = _run(["svnlook", "uuid", path])
    uuid = result.stdout.strip()

    # HEAD revision
    result = _run(["svnlook", "youngest", path])
    head_rev = int(result.stdout.strip())

    # Filesystem type
    fs_type = "fsfs"
    db_dir = os.path.join(path, "db")
    fs_type_file = os.path.join(db_dir, "fs-type")
    if os.path.exists(fs_type_file):
        with open(fs_type_file) as f:
            fs_type = f.read().strip()

    # Size (best effort)
    size: int | None = None
    try:
        size = sum(
            f.stat().st_size
            for f in Path(path).rglob("*")
            if f.is_file()
        )
    except OSError:
        pass

    return RepoInfo(
        name=os.path.basename(path),
        path=path,
        uuid=uuid,
        head_revision=head_rev,
        fs_type=fs_type,
        size_bytes=size,
    )


def delete_repo(path: str, backup_first: bool = True) -> str | None:
    """Delete a repository, optionally backing it up first.

    Args:
        path: Full path to the repository.
        backup_first: If True, hotcopy to path.bak before deleting.

    Returns:
        Backup path if backup was made, else None.
    """
    if not os.path.isdir(path):
        raise SvnNotFoundError(f"Repository not found: {path}")

    backup_path: str | None = None
    if backup_first:
        backup_path = f"{path}.bak"
        hotcopy(path, backup_path)
        logger.info("Backed up %s to %s", path, backup_path)

    shutil.rmtree(path)
    logger.info("Deleted repository: %s", path)
    return backup_path


def dump(
    repo_path: str,
    output_file: str,
    incremental: bool = False,
    lower_rev: int | None = None,
    upper_rev: int | None = None,
) -> str:
    """Dump a repository to a file.

    Args:
        repo_path: Path to the repository.
        output_file: Destination file path.
        incremental: If True, produce an incremental dump.
        lower_rev: Start revision for range dump.
        upper_rev: End revision for range dump.

    Returns:
        The output file path.
    """
    args = ["svnadmin", "dump", repo_path]
    if incremental:
        args.append("--incremental")
    if lower_rev is not None and upper_rev is not None:
        args.extend(["-r", f"{lower_rev}:{upper_rev}"])

    try:
        with open(output_file, "wb") as f_out:
            # Bypass run_sync to stream binary output directly to a file,
            # avoiding memory issues and encoding errors.
            result = subprocess.run(
                args, stdout=f_out, stderr=subprocess.PIPE, check=False
            )
            if result.returncode != 0:
                raise SvnCommandError(
                    command=" ".join(args),
                    exit_code=result.returncode,
                    stderr=result.stderr.decode(errors="replace"),
                )
        logger.info("Dumped %s to %s", repo_path, output_file)
    except OSError as e:
        raise SvnCommandError(command=" ".join(args), exit_code=-1, stderr=str(e)) from e
    return output_file


def load(repo_path: str, input_file: str) -> CommandResult:
    """Load a dump file into a repository.

    Args:
        repo_path: Path to the target repository.
        input_file: Path to the dump file.

    Returns:
        CommandResult from the load operation.
    """
    args = ["svnadmin", "load", repo_path]
    try:
        with open(input_file, "rb") as f_in:
            # Bypass run_sync to stream binary input directly from a file.
            result = subprocess.run(args, stdin=f_in, capture_output=True, check=False)
            if result.returncode != 0:
                raise SvnCommandError(
                    command=" ".join(args),
                    exit_code=result.returncode,
                    stderr=result.stderr.decode(errors="replace"),
                )
        logger.info("Loaded %s into %s", input_file, repo_path)
        return CommandResult(True, result.stdout.decode(errors="replace"), "", 0)
    except OSError as e:
        raise SvnCommandError(command=" ".join(args), exit_code=-1, stderr=str(e)) from e


def hotcopy(repo_path: str, dest_path: str) -> CommandResult:
    """Create a hot copy of a repository.

    Args:
        repo_path: Source repository path.
        dest_path: Destination path.

    Returns:
        CommandResult from the hotcopy operation.
    """
    return _run(["svnadmin", "hotcopy", repo_path, dest_path])


def verify(repo_path: str) -> bool:
    """Verify repository integrity.

    Args:
        repo_path: Path to the repository.

    Returns:
        True if verification passes.
    """
    result = run_sync(["svnadmin", "verify", repo_path])
    return result.success

def check_group_exists(group_name: str) -> bool:
    """Check if a system group exists using 'getent'."""
    try:
        # We use subprocess.run directly as it's a simple, safe system check.
        subprocess.run(
            ["getent", "group", group_name],
            check=True, capture_output=True, text=True, timeout=2
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        # CalledProcessError means getent ran but didn't find the group (exit code > 0).
        # FileNotFoundError means getent command is not on the system.
        return False


def check_user_exists(user_name: str) -> bool:
    """Check if a system user exists using 'getent'."""
    try:
        subprocess.run(
            ["getent", "passwd", user_name],
            check=True, capture_output=True, text=True, timeout=2
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False