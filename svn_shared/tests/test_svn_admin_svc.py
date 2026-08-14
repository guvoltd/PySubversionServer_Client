"""Tests for svn_shared.svn_admin_svc module."""

import os
from unittest.mock import patch

import pytest

from svn_shared.svn_admin_svc import (
    create_repo,
    delete_repo,
    list_repos,
    repo_info,
    verify,
)
from svn_shared.svn_command import CommandResult


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(args=["svnadmin"], exit_code=0, stdout=stdout, stderr="")


def _fail(stderr: str = "error") -> CommandResult:
    return CommandResult(args=["svnadmin"], exit_code=1, stdout="", stderr=stderr)


class TestCreateRepo:
    @patch("svn_shared.svn_admin_svc.run_sync")
    def test_basic_create(self, mock_run, tmp_path):
        mock_run.return_value = _ok()
        path = create_repo(str(tmp_path), "test-repo")
        assert path == os.path.join(str(tmp_path), "test-repo")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "svnadmin" in args[0]
        assert "create" in args

    @patch("svn_shared.svn_admin_svc.run_sync")
    def test_standard_layout(self, mock_run, tmp_path):
        mock_run.return_value = _ok()
        create_repo(str(tmp_path), "test-repo", standard_layout=True)
        # Should be called twice: create + mkdir
        assert mock_run.call_count == 2


class TestListRepos:
    def test_empty_dir(self, tmp_path):
        repos = list_repos(str(tmp_path))
        assert repos == []

    @patch("svn_shared.svn_admin_svc.repo_info")
    def test_finds_repos(self, mock_info, tmp_path):
        # Create a fake repo directory with a format file
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        (repo_dir / "format").write_text("5\n")

        from svn_shared.svn_admin_svc import RepoInfo
        mock_info.return_value = RepoInfo(
            name="my-repo",
            path=str(repo_dir),
            uuid="test-uuid",
            head_revision=10,
            fs_type="fsfs",
        )

        repos = list_repos(str(tmp_path))
        assert len(repos) == 1
        assert repos[0].name == "my-repo"


class TestRepoInfo:
    @patch("svn_shared.svn_admin_svc.run_sync")
    def test_parses_info(self, mock_run, tmp_path):
        # Create minimal repo structure
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        db_dir = repo_dir / "db"
        db_dir.mkdir()
        (db_dir / "fs-type").write_text("fsfs\n")

        mock_run.side_effect = [
            _ok("a1b2c3d4-uuid\n"),  # svnlook uuid
            _ok("42\n"),              # svnlook youngest
        ]

        info = repo_info(str(repo_dir))
        assert info.uuid == "a1b2c3d4-uuid"
        assert info.head_revision == 42
        assert info.fs_type == "fsfs"


class TestDeleteRepo:
    @patch("svn_shared.svn_admin_svc.hotcopy")
    def test_with_backup(self, mock_hotcopy, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "format").write_text("5\n")

        mock_hotcopy.return_value = _ok()

        backup = delete_repo(str(repo_dir), backup_first=True)
        assert backup == f"{repo_dir}.bak"
        assert not repo_dir.exists()

    def test_without_backup(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "format").write_text("5\n")

        backup = delete_repo(str(repo_dir), backup_first=False)
        assert backup is None
        assert not repo_dir.exists()


class TestVerify:
    @patch("svn_shared.svn_admin_svc.run_sync")
    def test_success(self, mock_run):
        mock_run.return_value = _ok()
        assert verify("/tmp/repo") is True

    @patch("svn_shared.svn_admin_svc.run_sync")
    def test_failure(self, mock_run):
        mock_run.return_value = _fail()
        assert verify("/tmp/repo") is False
