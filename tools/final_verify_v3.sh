#!/bin/bash
set -euo pipefail
cd /home/alexey/dev/kunipy

echo "=== sync fixed files from Windows ==="
for f in src/application/cli/diary_cli.py src/application/cli/monitor_cli.py pyproject.toml src/proxy_server.py src/infrastructure/memory/sleep_consolidation.py; do
    WIN="/mnt/g/AI/kunipy-main/$f"
    if [ -f "$WIN" ]; then
        cp -f "$WIN" "$f"
        echo "  synced: $f"
    fi
done

echo ""
echo "=== ruff critical rules (F821, B023, ASYNC230, DTZ006) ==="
.venv/bin/ruff check src/ --select F821,B023,ASYNC230,DTZ006 2>&1 || true

echo ""
echo "=== ruff statistics ==="
.venv/bin/ruff check src/ --statistics 2>&1 || true

echo ""
echo "=== import sanity ==="
.venv/bin/python3 -c "
from src.infrastructure.memory import (
    MemoryService, MemoryStore, WorkingMemory,
    MemoryLinkRepository, UserPreferenceRepository, MemoryTagRepository,
    DiaryContextInjector, SleepConsolidationService,
)
from src.di.container import create_dependencies, Dependencies
from src.config import load_config
from src.application.cli.diary_cli import cmd_list
from src.application.cli.monitor_cli import cmd_status
print('all imports OK')
"

echo ""
echo "=== dead code check ==="
grep -rn 'postgres_database\|UniversalDBAdapter\|postgres_adapter\|async_postgres\|working_memory_repository\|working_memory_extractor' src/ tools/ --include='*.py' 2>/dev/null | grep -v '\.pyc\|egg-info' || echo "CLEAN"

echo ""
echo "=== run memory_minimal.py ==="
.venv/bin/python3 test_memory_minimal.py 2>&1 || true

echo ""
echo "=== SQLite schema completeness ==="
.venv/bin/python3 -c "
import sqlite3, os
db_path = 'data/test_memory.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
    names = [t[0] for t in tables]
    for needed in ['memory_links', 'user_preferences', 'memory_tags', 'memory_pieces', 'memory_embeddings', 'conversations', 'users', 'chats']:
        status = 'OK' if needed in names else 'MISSING'
        print(f'  {status}: {needed}')
    conn.close()
else:
    print(f'{db_path} not found (expected from test_memory_minimal)')
"

echo ""
echo "=== Phase 2/4 wiring in container.py ==="
grep -c 'consolidation_service\|diary_context_injector' src/di/container.py
echo "  (expected: >= 6)"

echo ""
echo "DONE"
