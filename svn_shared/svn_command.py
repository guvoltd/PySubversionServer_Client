"""Async subprocess wrapper for SVN CLI commands.

This module provides the core command execution layer used by all SVN
service classes. It wraps subprocess.Popen with output capture, timeout,
cancellation, and input validation.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# Characters that should never appear in SVN CLI arguments.
_SHELL_META = re.compile(r"[;&|`$(){}!<>]")


@dataclass
class CommandResult:
    """Result of a completed SVN command."""

    args: list[str]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class RunningCommand:
    """Handle to a running subprocess, supports cancellation."""

    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    _cancelled: bool = field(default=False, init=False)

    def cancel(self) -> None:
        """Request cancellation of the running command."""
        self._cancelled = True
        if self.process and self.process.poll() is None:
            logger.info("Cancelling subprocess PID %s", self.process.pid)
            self.process.terminate()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


def validate_args(args: list[str]) -> None:
    """Validate command arguments to prevent shell injection.

    Args:
        args: List of command-line arguments.

    Raises:
        ValueError: If args is empty or contains shell metacharacters.
    """
    if not args:
        raise ValueError("Command arguments must not be empty")
    for i, arg in enumerate(args):
        if _SHELL_META.search(arg):
            raise ValueError(
                f"Argument {i} contains disallowed shell metacharacter: {arg!r}"
            )


def run_sync(
    args: list[str],
    cwd: str | None = None,
    timeout: float | None = None,
    stdin_data: str | None = None,
) -> CommandResult:
    """Run an SVN command synchronously and return the result.

    Args:
        args: Command and arguments, e.g. ["svn", "status", "--xml"].
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait. None means no limit.
        stdin_data: Optional string to send to the process stdin.

    Returns:
        CommandResult with exit code, stdout, and stderr.

    Raises:
        ValueError: If args are invalid.
        TimeoutError: If the command exceeds the timeout.
    """
    validate_args(args)
    logger.debug("run_sync: %s (cwd=%s)", args, cwd)

    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_data else subprocess.DEVNULL,
            text=True,
        )
        stdout, stderr = proc.communicate(input=stdin_data, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise TimeoutError(
            f"Command timed out after {timeout}s: {' '.join(args)}"
        ) from exc

    result = CommandResult(
        args=args,
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    logger.debug("run_sync result: exit_code=%d", result.exit_code)
    return result


def run_async(
    args: list[str],
    cwd: str | None = None,
    on_line: Callable[[str], None] | None = None,
    on_finished: Callable[[CommandResult], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    timeout: float | None = None,
) -> RunningCommand:
    """Run an SVN command asynchronously in a background thread.

    Output lines are delivered via the on_line callback as they arrive.
    When the command completes, on_finished is called with the full result.

    Args:
        args: Command and arguments.
        cwd: Working directory.
        on_line: Called for each stdout line as it arrives.
        on_finished: Called when the command completes.
        on_error: Called if an exception occurs.
        timeout: Maximum seconds to wait. None means no limit.

    Returns:
        RunningCommand handle that can be used to cancel the operation.

    Raises:
        ValueError: If args are invalid (raised immediately, not in thread).
    """
    validate_args(args)
    handle = RunningCommand()

    def _worker() -> None:
        logger.debug("run_async start: %s (cwd=%s)", args, cwd)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        try:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
            )
            handle.process = proc

            # Read stdout line by line for progress reporting.
            assert proc.stdout is not None
            for line in proc.stdout:
                if handle.is_cancelled:
                    break
                stripped = line.rstrip("\n")
                stdout_lines.append(stripped)
                if on_line:
                    on_line(stripped)

            # Collect any remaining stderr.
            assert proc.stderr is not None
            stderr_lines = proc.stderr.read().splitlines()

            proc.wait(timeout=timeout)

            result = CommandResult(
                args=args,
                exit_code=proc.returncode,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
            )
            logger.debug("run_async finished: exit_code=%d", result.exit_code)
            if on_finished:
                on_finished(result)

        except Exception as exc:
            logger.exception("run_async error: %s", exc)
            if on_error:
                on_error(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return handle
