#!/bin/bash
# pre-commit hook: reject files larger than MAX_SIZE bytes.
REPOS="$1"
TXN="$2"
MAX_SIZE=10485760  # 10 MB

CHANGED=$(svnlook changed -t "$TXN" "$REPOS" | grep "^[AU]" | awk '{print $2}')

for FILE in $CHANGED; do
    SIZE=$(svnlook filesize -t "$TXN" "$REPOS" "$FILE" 2>/dev/null)
    if [ -n "$SIZE" ] && [ "$SIZE" -gt "$MAX_SIZE" ]; then
        echo "File '$FILE' is ${SIZE} bytes (limit: ${MAX_SIZE})." >&2
        exit 1
    fi
done

exit 0
