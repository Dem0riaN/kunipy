#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

IDENTICAL=0
DIFFERENT=0
ONLY_IN_WSL=0
WSL_NEWER=()

while IFS= read -r f; do
    win="/mnt/g/AI/kunipy-main/${f#./}"
    if [ ! -f "$win" ]; then
        ONLY_IN_WSL=$((ONLY_IN_WSL + 1))
        continue
    fi
    if cmp -s "$f" "$win"; then
        IDENTICAL=$((IDENTICAL + 1))
    else
        DIFFERENT=$((DIFFERENT + 1))
        wt=$(stat -c %Y "$win" 2>/dev/null || echo 0)
        ft=$(stat -c %Y "$f" 2>/dev/null || echo 0)
        if [ "$ft" -gt "$wt" ]; then
            WSL_NEWER+=("$f")
        fi
    fi
done < <(find . -type f \( -name '*.py' -o -name '*.toml' -o -name '*.md' -o -name '*.sh' \) \
    -not -path './.venv/*' -not -path '*/__pycache__/*' | sort)

echo "IDENTICAL: $IDENTICAL"
echo "DIFFERENT: $DIFFERENT"
echo "ONLY_IN_WSL: $ONLY_IN_WSL"
echo ""
echo "=== WSL version is NEWER than Windows (do NOT overwrite these) ==="
for f in "${WSL_NEWER[@]}"; do
    echo "  $f"
done
