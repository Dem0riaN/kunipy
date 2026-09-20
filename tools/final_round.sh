#!/bin/bash
set -euo pipefail
cd /home/alexey/dev/kunipy

echo "=== sync latest Windows changes ==="
for f in test_memory_minimal.py src/interfaces/memory.py src/infrastructure/memory/memory_repository.py; do
    WIN="/mnt/g/AI/kunipy-main/$f"
    [ -f "$WIN" ] && cp -f "$WIN" "$f" && echo "  synced: $f"
done

echo ""
echo "=== ruff final statistics ==="
.venv/bin/ruff check src/ --statistics 2>&1 || true

echo ""
echo "=== ruff critical errors only (E/F categories) ==="
.venv/bin/ruff check src/ --select E9,F63,F7,F82 2>&1 || echo "CLEAN"

echo ""
echo "=== test_memory_minimal.py ==="
rm -f data/test_memory.db*
.venv/bin/python3 test_memory_minimal.py

echo ""
echo "=== test_memory_integration.py (no LLM needed) ==="
rm -f data/test_integration.db*
.venv/bin/python3 test_memory_integration.py 2>&1 | tail -30

echo ""
echo "=== compile check (all src/*.py) ==="
FAIL=0
for f in $(find src/ -name '*.py' | head -100); do
    .venv/bin/python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null || { echo "FAIL: $f"; FAIL=$((FAIL+1)); }
done
echo "Compile failures: $FAIL"

echo ""
echo "=== SQLite schema in test_integration.db ==="
if [ -f data/test_integration.db ]; then
    .venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('data/test_integration.db')
tables = [t[0] for t in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
for needed in ['memory_links', 'user_preferences', 'memory_tags', 'memory_pieces', 'memory_embeddings', 'conversations', 'users', 'chats']:
    print(f'  {\"OK\" if needed in tables else \"MISSING\"}: {needed}')
conn.close()
"
else
    echo "  test_integration.db not created (test may have failed early)"
fi

echo ""
echo "=== sync ALL modified WSL files back to Windows ==="
for f in src/application/cli/diary_cli.py src/application/cli/monitor_cli.py src/infrastructure/memory/sleep_consolidation.py src/proxy_server.py src/di/container.py src/memory_integrated_worker.py src/worker.py src/app.py src/diary.py src/infrastructure/memory/__init__.py; do
    [ -f "$f" ] && cp -f "$f" "/mnt/g/AI/kunipy-main/$f" && echo "  WSL→WIN: $f"
done

echo ""
echo "=== ALL CHECKS DONE ==="
