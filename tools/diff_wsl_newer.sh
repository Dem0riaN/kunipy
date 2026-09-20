#!/bin/bash
cd /home/alexey/dev/kunipy
for f in src/app.py src/diary.py src/proxy_server.py src/worker.py; do
    echo "=== $f ==="
    w="/mnt/g/AI/kunipy-main/$f"
    echo "WSL lines: $(wc -l < "$f") | WIN lines: $(wc -l < "$w")"
    echo "WSL mtime: $(stat -c '%y' "$f") | WIN mtime: $(stat -c '%y' "$w")"
    diff -u "$w" "$f" | head -30
    echo ""
done
