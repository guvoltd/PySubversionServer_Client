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
