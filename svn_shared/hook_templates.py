"""Hook template manager — install, enable, disable SVN repository hooks.

Provides built-in hook script templates and manages hook lifecycle
within SVN repositories.
"""

from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Built-in templates are loaded from the svn_server resources directory,
# but this module also ships a few defaults as strings for standalone use.

_BUILTIN_TEMPLATES: dict[str, tuple[str, str]] = {
    "pre-commit-msg-check": (
        "Reject commits with empty or short messages",
        """\
#!/bin/bash
# pre-commit hook: reject commits with empty or too-short messages.
REPOS="$1"
TXN="$2"

MSG=$(svnlook log -t "$TXN" "$REPOS")
MSG_LEN=${#MSG}

if [ "$MSG_LEN" -lt 10 ]; then
    echo "Commit message must be at least 10 characters." >&2
    exit 1
fi

exit 0
""",
    ),
    "post-commit-email": (
        "Send email notification after each commit",
        """\
#!/bin/bash
# post-commit hook: send email notification.
REPOS="$1"
REV="$2"

AUTHOR=$(svnlook author -r "$REV" "$REPOS")
LOG=$(svnlook log -r "$REV" "$REPOS")
CHANGED=$(svnlook changed -r "$REV" "$REPOS")

SUBJECT="[SVN] r${REV} by ${AUTHOR}"
BODY="Author: ${AUTHOR}\\nRevision: ${REV}\\n\\n${LOG}\\n\\nChanged paths:\\n${CHANGED}"

# Replace with your mail command / recipients.
# echo -e "$BODY" | mail -s "$SUBJECT" team@example.com

echo "Post-commit notification for r${REV} (email sending disabled by default)."
exit 0
""",
    ),
    "pre-commit-size-limit": (
        "Reject commits with files larger than a size limit",
        """\
#!/bin/bash
# pre-commit hook: reject files larger than MAX_SIZE bytes.
REPOS="$1"
TXN="$2"
MAX_SIZE=10485760  # 10 MB

CHANGED=$(svnlook changed -t "$TXN" "$REPOS" | grep "^[AU]" | awk '{print $2}')

for FILE in $CHANGED; do
    SIZE=$(svnlook filesize -t "$TXN" "$REPOS" "$FILE" 2>/dev/null)
    if [ -n "$SIZE" ] && [ "$SIZE" -gt "$MAX_SIZE" ]; then
        echo "File '$FILE' is ${SIZE} bytes, exceeding the ${MAX_SIZE}-byte limit." >&2
        exit 1
    fi
done

exit 0
""",
    ),
}


@dataclass
class HookTemplate:
    """A hook script template."""

    name: str
    description: str
    content: str


@dataclass
class HookInfo:
    """Info about an installed hook in a repository."""

    name: str
    enabled: bool
    path: str


def list_templates(extra_dir: str | None = None) -> list[HookTemplate]:
    """List all available hook templates.

    Args:
        extra_dir: Optional directory with additional .sh template files.

    Returns:
        List of HookTemplate objects.
    """
    templates: list[HookTemplate] = []

    # Built-in templates.
    for name, (desc, content) in _BUILTIN_TEMPLATES.items():
        templates.append(HookTemplate(name=name, description=desc, content=content))

    # Load from extra directory if provided.
    if extra_dir and os.path.isdir(extra_dir):
        for filename in sorted(os.listdir(extra_dir)):
            if filename.endswith(".sh"):
                filepath = os.path.join(extra_dir, filename)
                with open(filepath) as f:
                    content = f.read()
                tpl_name = filename.removesuffix(".sh")
                # First comment line as description.
                desc = ""
                for line in content.splitlines():
                    if line.startswith("#") and not line.startswith("#!"):
                        desc = line.lstrip("# ").strip()
                        break
                templates.append(HookTemplate(name=tpl_name, description=desc, content=content))

    return templates


def get_template(name: str) -> HookTemplate | None:
    """Get a specific built-in template by name."""
    if name in _BUILTIN_TEMPLATES:
        desc, content = _BUILTIN_TEMPLATES[name]
        return HookTemplate(name=name, description=desc, content=content)
    return None


def list_hooks(repo_path: str) -> list[HookInfo]:
    """List hooks in a repository.

    Args:
        repo_path: Path to the SVN repository.

    Returns:
        List of HookInfo objects.
    """
    hooks_dir = os.path.join(repo_path, "hooks")
    if not os.path.isdir(hooks_dir):
        return []

    known_hooks = [
        "pre-commit", "post-commit",
        "pre-revprop-change", "post-revprop-change",
        "pre-lock", "post-lock",
        "pre-unlock", "post-unlock",
        "start-commit",
    ]

    result: list[HookInfo] = []
    for hook_name in known_hooks:
        hook_path = os.path.join(hooks_dir, hook_name)
        tmpl_path = f"{hook_path}.tmpl"

        if os.path.exists(hook_path):
            result.append(HookInfo(name=hook_name, enabled=True, path=hook_path))
        elif os.path.exists(tmpl_path):
            result.append(HookInfo(name=hook_name, enabled=False, path=tmpl_path))

    return result


def install_hook(repo_path: str, hook_name: str, content: str) -> str:
    """Install a hook script into a repository.

    Args:
        repo_path: Path to the SVN repository.
        hook_name: Hook name (e.g. "pre-commit").
        content: Script content.

    Returns:
        Path to the installed hook file.
    """
    hooks_dir = os.path.join(repo_path, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    hook_path = os.path.join(hooks_dir, hook_name)
    with open(hook_path, "w") as f:
        f.write(content)

    # Make executable.
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    logger.info("Installed hook %s at %s", hook_name, hook_path)
    return hook_path


def enable_hook(repo_path: str, hook_name: str) -> None:
    """Enable a disabled hook (remove .tmpl suffix)."""
    hooks_dir = os.path.join(repo_path, "hooks")
    tmpl_path = os.path.join(hooks_dir, f"{hook_name}.tmpl")
    hook_path = os.path.join(hooks_dir, hook_name)

    if os.path.exists(tmpl_path) and not os.path.exists(hook_path):
        os.rename(tmpl_path, hook_path)
        st = os.stat(hook_path)
        os.chmod(hook_path, st.st_mode | stat.S_IEXEC)
        logger.info("Enabled hook: %s", hook_name)


def disable_hook(repo_path: str, hook_name: str) -> None:
    """Disable an active hook (add .tmpl suffix)."""
    hooks_dir = os.path.join(repo_path, "hooks")
    hook_path = os.path.join(hooks_dir, hook_name)
    tmpl_path = os.path.join(hooks_dir, f"{hook_name}.tmpl")

    if os.path.exists(hook_path) and not os.path.exists(tmpl_path):
        os.rename(hook_path, tmpl_path)
        logger.info("Disabled hook: %s", hook_name)
