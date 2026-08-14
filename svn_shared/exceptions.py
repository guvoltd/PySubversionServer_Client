"""Shared exception types for SVN Desktop Suite."""


class SvnSuiteError(Exception):
    """Base exception for all SVN Suite errors."""


class SvnCommandError(SvnSuiteError):
    """Raised when an SVN CLI command fails."""

    def __init__(self, command: str, exit_code: int, stderr: str) -> None:
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"SVN command failed (exit {exit_code}): {stderr.strip()}")


class SvnAuthError(SvnCommandError):
    """Raised when SVN authentication fails."""


class SvnConflictError(SvnSuiteError):
    """Raised when a working copy has unresolved conflicts."""

    def __init__(self, paths: list[str]) -> None:
        self.paths = paths
        super().__init__(f"Unresolved conflicts in {len(paths)} file(s)")


class SvnNotFoundError(SvnSuiteError):
    """Raised when a working copy or repository path does not exist."""


class ConfigParseError(SvnSuiteError):
    """Raised when an SVN config file cannot be parsed."""

    def __init__(self, path: str, line: int | None = None, detail: str = "") -> None:
        self.path = path
        self.line = line
        self.detail = detail
        loc = f" (line {line})" if line else ""
        super().__init__(f"Failed to parse {path}{loc}: {detail}")


class CredentialError(SvnSuiteError):
    """Raised when credential storage/retrieval fails."""
