"""Tests for svn_shared.svn_command module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from svn_shared.svn_command import (
    CommandResult,
    RunningCommand,
    run_async,
    run_sync,
    validate_args,
)


class TestValidateArgs:
    def test_empty_args_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_args([])

    def test_valid_args_pass(self):
        validate_args(["svn", "status", "--xml"])

    def test_shell_metachar_semicolon(self):
        with pytest.raises(ValueError, match="disallowed"):
            validate_args(["svn", "info", ";rm -rf /"])

    def test_shell_metachar_pipe(self):
        with pytest.raises(ValueError, match="disallowed"):
            validate_args(["svn", "log", "| cat"])

    def test_shell_metachar_backtick(self):
        with pytest.raises(ValueError, match="disallowed"):
            validate_args(["svn", "`whoami`"])

    def test_paths_with_spaces_ok(self):
        validate_args(["svn", "add", "/home/user/my project/file.txt"])

    def test_revision_numbers_ok(self):
        validate_args(["svn", "log", "-r", "1:HEAD"])


class TestRunSync:
    @patch("svn_shared.svn_command.subprocess.Popen")
    def test_successful_command(self, mock_popen):
        proc = MagicMock()
        proc.communicate.return_value = ("output line\n", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        result = run_sync(["svn", "info"])

        assert result.success
        assert result.exit_code == 0
        assert "output line" in result.stdout
        assert result.stderr == ""

    @patch("svn_shared.svn_command.subprocess.Popen")
    def test_failed_command(self, mock_popen):
        proc = MagicMock()
        proc.communicate.return_value = ("", "svn: E170013: error\n")
        proc.returncode = 1
        mock_popen.return_value = proc

        result = run_sync(["svn", "checkout", "bad://url"])

        assert not result.success
        assert result.exit_code == 1
        assert "error" in result.stderr

    @patch("svn_shared.svn_command.subprocess.Popen")
    def test_timeout_raises(self, mock_popen):
        proc = MagicMock()
        # First call raises TimeoutExpired; second call (after kill) returns normally.
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="svn", timeout=5),
            ("", ""),
        ]
        proc.kill.return_value = None
        mock_popen.return_value = proc

        with pytest.raises(TimeoutError, match="timed out"):
            run_sync(["svn", "checkout", "http://example.com"], timeout=5)

    def test_empty_args_raises(self):
        with pytest.raises(ValueError):
            run_sync([])

    @patch("svn_shared.svn_command.subprocess.Popen")
    def test_args_passed_as_list(self, mock_popen):
        """Verify args are passed as a list, not a string (no shell=True)."""
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        run_sync(["svn", "status", "--xml"])

        call_args = mock_popen.call_args
        assert call_args[0][0] == ["svn", "status", "--xml"]
        # shell should not be True (it's not passed, defaulting to False)
        assert call_args[1].get("shell", False) is False


class TestRunAsync:
    def test_empty_args_raises(self):
        with pytest.raises(ValueError):
            run_async([])

    @patch("svn_shared.svn_command.subprocess.Popen")
    def test_callback_invoked(self, mock_popen):
        proc = MagicMock()
        proc.stdout = iter(["line1\n", "line2\n"])
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = ""
        proc.wait.return_value = None
        proc.returncode = 0
        proc.poll.return_value = None
        mock_popen.return_value = proc

        lines = []
        finished_results = []

        import threading

        done = threading.Event()

        def on_line(line):
            lines.append(line)

        def on_finished(result):
            finished_results.append(result)
            done.set()

        handle = run_async(
            ["svn", "log"],
            on_line=on_line,
            on_finished=on_finished,
        )

        done.wait(timeout=5)
        assert len(lines) == 2
        assert len(finished_results) == 1
        assert finished_results[0].exit_code == 0


class TestRunningCommand:
    def test_cancel(self):
        handle = RunningCommand()
        proc = MagicMock()
        proc.poll.return_value = None
        handle.process = proc

        handle.cancel()

        assert handle.is_cancelled
        proc.terminate.assert_called_once()
