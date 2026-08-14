"""Parser for SVN configuration files (svnserve.conf, authz, passwd).

Preserves comments and ordering on round-trip. Creates a .bak backup
before writing any changes.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field

from svn_shared.exceptions import ConfigParseError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SvnserveConfig:
    """Parsed svnserve.conf settings."""

    anon_access: str = "none"
    auth_access: str = "write"
    password_db: str = "passwd"
    authz_db: str = "authz"
    realm: str = ""
    raw_lines: list[str] = field(default_factory=list, repr=False)


@dataclass
class AuthzRule:
    """A single authorization rule."""

    section: str  # e.g. "[/]" or "[repo:/trunk]"
    user: str  # username or "*"
    permission: str  # "r", "rw", or ""


@dataclass
class PasswdEntry:
    """A user entry in the passwd file."""

    username: str
    password: str
    active: bool = True

# ---------------------------------------------------------------------------
# INI-like parser that preserves comments
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[(.+)\]\s*$")
_KV_RE = re.compile(r"^([^#=]+?)\s*=\s*(.*)$")


def _parse_ini_lines(lines: list[str]) -> list[tuple[str, str, str, str]]:
    """Parse INI lines into (type, section, key, value) tuples.

    type is one of: "section", "kv", "comment", "blank".
    """
    result: list[tuple[str, str, str, str]] = []
    current_section = ""
    for line in lines:
        stripped = line.rstrip("\n")
        if not stripped or stripped.isspace():
            result.append(("blank", current_section, "", stripped))
        elif stripped.lstrip().startswith("#"):
            result.append(("comment", current_section, "", stripped))
        else:
            m_section = _SECTION_RE.match(stripped)
            if m_section:
                current_section = m_section.group(1)
                result.append(("section", current_section, "", stripped))
            else:
                m_kv = _KV_RE.match(stripped)
                if m_kv:
                    key = m_kv.group(1).strip()
                    value = m_kv.group(2).strip()
                    result.append(("kv", current_section, key, value))
                else:
                    result.append(("comment", current_section, "", stripped))
    return result


def _backup(path: str) -> str:
    """Create a .bak backup of a file."""
    bak = f"{path}.bak"
    shutil.copy2(path, bak)
    logger.debug("Backed up %s to %s", path, bak)
    return bak


# ---------------------------------------------------------------------------
# svnserve.conf
# ---------------------------------------------------------------------------

def parse_svnserve_conf(path: str) -> SvnserveConfig:
    """Parse a svnserve.conf file.

    Args:
        path: Path to svnserve.conf.

    Returns:
        SvnserveConfig with parsed values.
    """
    if not os.path.exists(path):
        raise ConfigParseError(path, detail="File not found")

    with open(path) as f:
        lines = f.readlines()

    config = SvnserveConfig(raw_lines=[l.rstrip("\n") for l in lines])
    parsed = _parse_ini_lines(lines)

    for kind, section, key, value in parsed:
        if kind == "kv" and section == "general":
            if key == "anon-access":
                config.anon_access = value
            elif key == "auth-access":
                config.auth_access = value
            elif key == "password-db":
                config.password_db = value
            elif key == "authz-db":
                config.authz_db = value
            elif key == "realm":
                config.realm = value

    return config


def write_svnserve_conf(path: str, config: SvnserveConfig) -> None:
    """Write svnserve.conf, preserving comments and structure.

    This function will replace or add the managed keys to ensure they are
    correctly set and uncommented.

    Creates a .bak backup before writing.
    """
    if os.path.exists(path):
        _backup(path)

    desired_values = {
        "anon-access": config.anon_access,
        "auth-access": config.auth_access,
        "password-db": config.password_db,
        "authz-db": config.authz_db,
        "realm": config.realm,
    }

    source_lines = config.raw_lines or []
    output_lines: list[str] = []

    # Filter out any existing declarations of our managed keys
    for line in source_lines:
        stripped = line.rstrip()
        is_managed = False
        for key in desired_values:
            if re.match(rf"^\s*#?\s*{re.escape(key)}\s*=", stripped):
                is_managed = True
                break
        if not is_managed:
            output_lines.append(line)

    # Find where the [general] section is, or add it if it's missing.
    try:
        general_idx = next(i for i, line in enumerate(output_lines) if line.strip() == "[general]")
    except StopIteration:
        output_lines.insert(0, "[general]")
        general_idx = 0

    # Insert our managed keys right after the [general] header.
    # Inserting in reverse order of a sorted list keeps them in alphabetical order.
    for key in sorted(desired_values.keys(), reverse=True):
        output_lines.insert(general_idx + 1, f"{key} = {desired_values[key]}")

    with open(path, "w") as f:
        f.write("\n".join(output_lines) + "\n")
    logger.info("Wrote svnserve.conf: %s", path)


# ---------------------------------------------------------------------------
# authz
# ---------------------------------------------------------------------------

def parse_authz(path: str) -> list[AuthzRule]:
    """Parse an authz file into a list of rules.

    Args:
        path: Path to authz file.

    Returns:
        List of AuthzRule objects.
    """
    if not os.path.exists(path):
        raise ConfigParseError(path, detail="File not found")

    with open(path) as f:
        lines = f.readlines()

    rules: list[AuthzRule] = []
    parsed = _parse_ini_lines(lines)

    for kind, section, key, value in parsed:
        if kind == "kv" and section != "groups":
            rules.append(AuthzRule(
                section=f"[{section}]",
                user=key,
                permission=value,
            ))
    return rules


def parse_groups_from_authz(path: str) -> dict[str, list[str]]:
    """Parse the [groups] section of an authz file.

    Args:
        path: Path to authz file.

    Returns:
        Dictionary where keys are group names and values are lists of members.
    """
    if not os.path.exists(path):
        return {}

    groups: dict[str, list[str]] = {}
    in_groups_section = False
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped == "[groups]":
                in_groups_section = True
                continue
            if in_groups_section and stripped.startswith("["): # End of [groups] section
                break
            if in_groups_section and "=" in stripped and not stripped.startswith("#"):
                name, _, members_str = stripped.partition("=")
                groups[name.strip()] = [m.strip() for m in members_str.split(",") if m.strip()]
    return groups


def write_authz(path: str, rules: list[AuthzRule], preserve_source: str | None = None) -> None:
    """Write an authz file from rules.

    If preserve_source is given, comments and groups from that file are preserved.
    Creates a .bak backup before writing.
    """
    if os.path.exists(path):
        _backup(path)

    source_path = preserve_source or path
    groups: dict[str, list[str]] = {}
    if preserve_source and os.path.exists(source_path):
        groups = parse_groups_from_authz(source_path)

    # Group rules by section.
    sections: dict[str, list[tuple[str, str]]] = {}
    for rule in rules:
        section_name = rule.section.strip("[]")
        if section_name == "groups":
            continue  # Groups are handled separately to preserve them
        if section_name not in sections:
            sections[section_name] = []
        sections[section_name].append((rule.user, rule.permission))

    lines: list[str] = []
    if groups:
        lines.append("[groups]")
        for name, members in sorted(groups.items()):
            lines.append(f"{name} = {','.join(m for m in sorted(members))}")
        lines.append("")

    for section_name, entries in sorted(sections.items()):
        lines.append(f"[{section_name}]")
        for user, perm in sorted(entries):
            lines.append(f"{user} = {perm}")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Wrote authz: %s", path)


# ---------------------------------------------------------------------------
# passwd
# ---------------------------------------------------------------------------

def parse_passwd(path: str) -> list[PasswdEntry]:
    """Parse a passwd file.

    Args:
        path: Path to passwd file.

    Returns:
        List of PasswdEntry objects.
    """
    if not os.path.exists(path):
        raise ConfigParseError(path, detail="File not found")

    with open(path) as f:
        lines = f.readlines()

    entries: list[PasswdEntry] = []
    in_users_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[users]":
            in_users_section = True
            continue
        if in_users_section and stripped.startswith("["):
            break  # End of users section

        if in_users_section:
            is_commented = stripped.startswith("#")
            target_line = stripped.lstrip("#").strip()
            m_kv = _KV_RE.match(target_line)
            if m_kv:
                key = m_kv.group(1).strip()
                value = m_kv.group(2).strip()
                entries.append(PasswdEntry(username=key, password=value, active=not is_commented))

    return entries


def write_passwd(path: str, entries: list[PasswdEntry]) -> None:
    """Write a passwd file.

    Creates a .bak backup before writing.
    """
    if os.path.exists(path):
        _backup(path)

    lines = ["[users]"]
    for entry in entries:
        line = f"{entry.username} = {entry.password}"
        if not entry.active:
            line = f"# {line}"
        lines.append(line)
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Wrote passwd: %s", path)
