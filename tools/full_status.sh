#!/bin/bash
cd /home/alexey/dev/kunipy
echo "=== DIFFERENT files: which side is NEWER ==="
while IFS= read -r f; do
    win="/mnt/g/AI/kunipy-main/${f#./}"
    [ -f "$win" ] || continue
    cmp -s "$f" "$win" && continue
    wt=$(stat -c %Y "$win" 2>/dev/null || echo 0)
    ft=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    if [ "$ft" -gt "$wt" ]; then
        echo "WSL_NEWER  $f"
    else
        echo "WIN_NEWER  $f"
    fi
done < <(find . -type f \( -name '*.py' -o -name '*.toml' -o -name '*.md' -o -name '*.sh' \) \
    -not -path './.venv/*' -not -path '*/__pycache__/*' | sort)

echo ""
echo "=== ONLY IN WSL (not present on Windows) ==="
while IFS= read -r f; do
    win="/mnt/g/AI/kunipy-main/${f#./}"
    [ -f "$win" ] && continue
    echo "  $f"
done < <(find . -type f \( -name '*.py' -o -name '*.toml' -o -name '*.md' -o -name '*.sh' \) \
    -not -path './.venv/*' -not -path '*/__pycache__/*' | sort)

echo ""
echo "=== ONLY IN WINDOWS (not present in WSL) ==="
cd /mnt/g/AI/kunipy-main
while IFS= read -r f; do
    wslf="/home/alexey/dev/kunipy/${f#./}"
    [ -f "$wslf" ] && continue
    echo "  $f"
done < <(find . -type f \( -name '*.py' -o -name '*.toml' -o -name '*.md' -o -name '*.sh' \) \
    -not -path './.venv/*' -not -path '*/__pycache__/*' | sort)
