#!/bin/bash
# post-commit hook: send email notification after each commit.
REPOS="$1"
REV="$2"

AUTHOR=$(svnlook author -r "$REV" "$REPOS")
LOG=$(svnlook log -r "$REV" "$REPOS")
CHANGED=$(svnlook changed -r "$REV" "$REPOS")

SUBJECT="[SVN] r${REV} by ${AUTHOR}"
BODY="Author: ${AUTHOR}\nRevision: ${REV}\n\n${LOG}\n\nChanged:\n${CHANGED}"

# Uncomment and configure:
# echo -e "$BODY" | mail -s "$SUBJECT" team@example.com

echo "Post-commit notification for r${REV}."
exit 0
