"""Tests for svn_shared.svn_client_svc module."""

from unittest.mock import patch

import pytest

from svn_shared.exceptions import SvnAuthError, SvnCommandError
from svn_shared.svn_command import CommandResult
from svn_shared.svn_client_svc import (
    StatusEntry,
    commit,
    diff,
    info,
    log,
    status,
)


MOCK_STATUS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<status>
  <target path=".">
    <entry path="modified.py">
      <wc-status item="modified" props="none" revision="5" />
    </entry>
    <entry path="added.py">
      <wc-status item="added" props="none" />
    </entry>
    <entry path="deleted.py">
      <wc-status item="deleted" props="none" revision="3" />
    </entry>
  </target>
</status>
"""

MOCK_LOG_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<log>
  <logentry revision="42">
    <author>alice</author>
    <date>2026-04-30T10:00:00.000000Z</date>
    <paths>
      <path action="M">/trunk/main.py</path>
    </paths>
    <msg>Fix the thing</msg>
  </logentry>
  <logentry revision="41">
    <author>bob</author>
    <date>2026-04-29T09:00:00.000000Z</date>
    <paths>
      <path action="A">/trunk/new.py</path>
    </paths>
    <msg>Add new module</msg>
  </logentry>
</log>
"""

MOCK_INFO_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<info>
  <entry kind="dir" path="." revision="42">
    <url>file:///tmp/repo/trunk</url>
    <relative-url>^/trunk</relative-url>
    <repository>
      <root>file:///tmp/repo</root>
      <uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</uuid>
    </repository>
  </entry>
</info>
"""


def _ok(stdout: str) -> CommandResult:
    return CommandResult(args=["svn"], exit_code=0, stdout=stdout, stderr="")


def _fail(stderr: str, code: int = 1) -> CommandResult:
    return CommandResult(args=["svn"], exit_code=code, stdout="", stderr=stderr)


class TestStatus:
    @patch("svn_shared.svn_client_svc.run_sync")
    def test_parses_xml(self, mock_run):
        mock_run.return_value = _ok(MOCK_STATUS_XML)
        entries = status("/tmp/wc")

        assert len(entries) == 3
        assert entries[0].path == "modified.py"
        assert entries[0].status == "modified"
        assert entries[0].revision == 5
        assert entries[1].status == "added"
        assert entries[1].revision is None
        assert entries[2].status == "deleted"


class TestLog:
    @patch("svn_shared.svn_client_svc.run_sync")
    def test_parses_xml(self, mock_run):
        mock_run.return_value = _ok(MOCK_LOG_XML)
        entries = log("/tmp/wc", limit=10)

        assert len(entries) == 2
        assert entries[0].revision == 42
        assert entries[0].author == "alice"
        assert entries[0].message == "Fix the thing"
        assert len(entries[0].changed_paths) == 1
        assert entries[0].changed_paths[0].action == "M"
        assert entries[1].revision == 41


class TestCommit:
    @patch("svn_shared.svn_client_svc.run_sync")
    def test_returns_revision(self, mock_run):
        mock_run.return_value = _ok("Committed revision 43.\n")
        rev = commit("/tmp/wc", "test commit")
        assert rev == 43

    @patch("svn_shared.svn_client_svc.run_sync")
    def test_auth_failure(self, mock_run):
        mock_run.return_value = _fail("svn: E170013: Authorization failed")
        with pytest.raises(SvnAuthError):
            commit("/tmp/wc", "test")


class TestDiff:
    @patch("svn_shared.svn_client_svc.run_sync")
    def test_returns_diff_string(self, mock_run):
        mock_run.return_value = _ok("--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n")
        result = diff("/tmp/wc")
        assert "+new" in result
        assert "-old" in result


class TestInfo:
    @patch("svn_shared.svn_client_svc.run_sync")
    def test_parses_xml(self, mock_run):
        mock_run.return_value = _ok(MOCK_INFO_XML)
        wc = info("/tmp/wc")

        assert wc.url == "file:///tmp/repo/trunk"
        assert wc.relative_url == "^/trunk"
        assert wc.repo_root_url == "file:///tmp/repo"
        assert wc.repo_uuid == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert wc.revision == 42
