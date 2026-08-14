"""Tests for svn_shared.credential_mgr module."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from svn_shared.credential_mgr import delete, retrieve, store
from svn_shared.exceptions import CredentialError


@pytest.fixture
def mock_keyring():
    """Patch keyring module for testing.

    If keyring is not installed, we inject a fake module so the patch target exists.
    """
    # Ensure the credential_mgr module has a 'keyring' attribute to patch.
    import svn_shared.credential_mgr as cm

    fake_kr = MagicMock()
    fake_kr.errors = MagicMock()
    fake_kr.errors.KeyringError = Exception

    with patch.object(cm, "_KEYRING_AVAILABLE", True), \
         patch.object(cm, "keyring", fake_kr, create=True):
        yield fake_kr


class TestStore:
    def test_stores_credentials(self, mock_keyring):
        store("my-realm", "alice", "secret")
        assert mock_keyring.set_password.call_count == 2

    def test_unavailable_raises(self):
        with patch("svn_shared.credential_mgr._KEYRING_AVAILABLE", False):
            with pytest.raises(CredentialError, match="not installed"):
                store("realm", "user", "pass")


class TestRetrieve:
    def test_found(self, mock_keyring):
        mock_keyring.get_password.side_effect = lambda key, field: {
            "username": "alice",
            "password": "secret",
        }.get(field)

        cred = retrieve("my-realm")
        assert cred is not None
        assert cred.username == "alice"
        assert cred.password == "secret"

    def test_not_found(self, mock_keyring):
        mock_keyring.get_password.return_value = None
        cred = retrieve("missing-realm")
        assert cred is None

    def test_unavailable_returns_none(self):
        with patch("svn_shared.credential_mgr._KEYRING_AVAILABLE", False):
            assert retrieve("realm") is None


class TestDelete:
    def test_deletes(self, mock_keyring):
        delete("my-realm")
        assert mock_keyring.delete_password.call_count == 2

    def test_unavailable_noop(self):
        with patch("svn_shared.credential_mgr._KEYRING_AVAILABLE", False):
            delete("realm")  # Should not raise
