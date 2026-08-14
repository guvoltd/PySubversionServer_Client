"""Tests for svn_shared.config_parser module."""

import pytest

from svn_shared.config_parser import (
    parse_authz,
    parse_passwd,
    parse_svnserve_conf,
    write_authz,
    write_passwd,
    write_svnserve_conf,
)
from svn_shared.exceptions import ConfigParseError


SAMPLE_SVNSERVE_CONF = """\
# svnserve.conf
[general]
anon-access = read
auth-access = write
password-db = passwd
authz-db = authz
realm = My Test Realm
"""

SAMPLE_AUTHZ = """\
[groups]
devs = alice, bob

[/]
* = r
@devs = rw

[/secret]
* =
alice = rw
"""

SAMPLE_PASSWD = """\
[users]
alice = password123
bob = hunter2
"""


class TestSvnserveConf:
    def test_parse(self, tmp_path):
        conf_file = tmp_path / "svnserve.conf"
        conf_file.write_text(SAMPLE_SVNSERVE_CONF)

        config = parse_svnserve_conf(str(conf_file))
        assert config.anon_access == "read"
        assert config.auth_access == "write"
        assert config.password_db == "passwd"
        assert config.authz_db == "authz"
        assert config.realm == "My Test Realm"

    def test_write_preserves_comments(self, tmp_path):
        conf_file = tmp_path / "svnserve.conf"
        conf_file.write_text(SAMPLE_SVNSERVE_CONF)

        config = parse_svnserve_conf(str(conf_file))
        config.anon_access = "none"
        write_svnserve_conf(str(conf_file), config)

        # Backup should exist
        assert (tmp_path / "svnserve.conf.bak").exists()

        # Re-parse
        config2 = parse_svnserve_conf(str(conf_file))
        assert config2.anon_access == "none"
        assert config2.auth_access == "write"  # unchanged

    def test_file_not_found(self):
        with pytest.raises(ConfigParseError, match="not found"):
            parse_svnserve_conf("/nonexistent/svnserve.conf")


class TestAuthz:
    def test_parse(self, tmp_path):
        authz_file = tmp_path / "authz"
        authz_file.write_text(SAMPLE_AUTHZ)

        rules = parse_authz(str(authz_file))
        assert len(rules) >= 3
        root_rules = [r for r in rules if r.section == "[/]"]
        assert any(r.user == "*" and r.permission == "r" for r in root_rules)
        assert any(r.user == "@devs" and r.permission == "rw" for r in root_rules)

    def test_write_and_reparse(self, tmp_path):
        authz_file = tmp_path / "authz"
        authz_file.write_text(SAMPLE_AUTHZ)

        rules = parse_authz(str(authz_file))
        write_authz(str(authz_file), rules)

        # Backup should exist
        assert (tmp_path / "authz.bak").exists()

        rules2 = parse_authz(str(authz_file))
        assert len(rules2) == len(rules)


class TestPasswd:
    def test_parse(self, tmp_path):
        passwd_file = tmp_path / "passwd"
        passwd_file.write_text(SAMPLE_PASSWD)

        entries = parse_passwd(str(passwd_file))
        assert len(entries) == 2
        assert entries[0].username == "alice"
        assert entries[1].username == "bob"

    def test_write_and_reparse(self, tmp_path):
        passwd_file = tmp_path / "passwd"
        passwd_file.write_text(SAMPLE_PASSWD)

        entries = parse_passwd(str(passwd_file))
        write_passwd(str(passwd_file), entries)

        assert (tmp_path / "passwd.bak").exists()

        entries2 = parse_passwd(str(passwd_file))
        assert len(entries2) == 2
        assert entries2[0].username == "alice"
