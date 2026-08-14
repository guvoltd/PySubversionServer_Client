"""Credential manager — stores/retrieves SVN credentials via OS keyring.

Uses the `keyring` library which integrates with GNOME Keyring, KDE Wallet,
or other Secret Service API providers on Linux.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from svn_shared.exceptions import CredentialError

logger = logging.getLogger(__name__)

_SERVICE_NAME = "svn-desktop-suite"

try:
    import keyring
    import keyring.errors

    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False
    logger.warning("keyring library not installed — credential storage unavailable")


@dataclass
class Credential:
    """A stored SVN credential."""

    realm: str
    username: str
    password: str


def is_available() -> bool:
    """Check if keyring backend is available."""
    if not _KEYRING_AVAILABLE:
        return False
    try:
        backend = keyring.get_keyring()
        # The fail backend means no real keyring is configured.
        return "fail" not in type(backend).__name__.lower()
    except Exception:
        return False


def store(realm: str, username: str, password: str) -> None:
    """Store credentials for an SVN realm.

    Args:
        realm: SVN authentication realm string.
        username: Username.
        password: Password.

    Raises:
        CredentialError: If keyring is unavailable or storage fails.
    """
    if not _KEYRING_AVAILABLE:
        raise CredentialError("keyring library is not installed")

    key = f"{_SERVICE_NAME}:{realm}"
    try:
        # Store username and password as separate entries.
        keyring.set_password(key, "username", username)
        keyring.set_password(key, "password", password)
        logger.info("Stored credentials for realm: %s", realm)
    except keyring.errors.KeyringError as exc:
        raise CredentialError(f"Failed to store credentials: {exc}") from exc


def retrieve(realm: str) -> Credential | None:
    """Retrieve credentials for an SVN realm.

    Args:
        realm: SVN authentication realm string.

    Returns:
        Credential if found, None otherwise.
    """
    if not _KEYRING_AVAILABLE:
        return None

    key = f"{_SERVICE_NAME}:{realm}"
    try:
        username = keyring.get_password(key, "username")
        password = keyring.get_password(key, "password")
        if username and password:
            return Credential(realm=realm, username=username, password=password)
        return None
    except keyring.errors.KeyringError as exc:
        logger.warning("Failed to retrieve credentials for %s: %s", realm, exc)
        return None


def delete(realm: str) -> None:
    """Delete stored credentials for an SVN realm.

    Args:
        realm: SVN authentication realm string.
    """
    if not _KEYRING_AVAILABLE:
        return

    key = f"{_SERVICE_NAME}:{realm}"
    try:
        keyring.delete_password(key, "username")
        keyring.delete_password(key, "password")
        logger.info("Deleted credentials for realm: %s", realm)
    except keyring.errors.KeyringError as exc:
        logger.warning("Failed to delete credentials for %s: %s", realm, exc)
