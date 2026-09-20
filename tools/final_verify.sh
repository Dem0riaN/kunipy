#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

echo "=== Step 1: Import check ==="
.venv/bin/python3 -c "
from src.infrastructure.memory import (
    MemoryService, MemoryStore, WorkingMemory,
    MemoryLinkRepository, UserPreferenceRepository, MemoryTagRepository,
    DiaryContextInjector, SleepConsolidationService,
    ConversationRepository, MemoryRepository, MemoryDatabase,
    UserRepository, ChatRepository, DiaryDumpService,
)
print('  OK: all imports successful')
" 2>&1

echo ""
echo "=== Step 2: Fix stale tools/export_memory.py ==="
if grep -q "PostgreSQLDatabase\|UniversalDBAdapter" tools/export_memory.py 2>/dev/null; then
  cp /mnt/g/AI/kunipy-main/export_memory.py tools/export_memory.py
  echo "  FIXED: tools/export_memory.py (copied clean WIN version)"
else
  echo "  OK: tools/export_memory.py already clean"
fi

echo ""
echo "=== Step 3: Fix stale tools/migrate_kuni.py ==="
if grep -q "PostgreSQLDatabase\|UniversalDBAdapter" tools/migrate_kuni.py 2>/dev/null; then
  cp /mnt/g/AI/kunipy-main/migrate_kuni.py tools/migrate_kuni.py
  echo "  FIXED: tools/migrate_kuni.py (copied clean WIN version)"
else
  echo "  OK: tools/migrate_kuni.py already clean"
fi

echo ""
echo "=== Step 4: Delete working_memory_repository.py (dead code) ==="
if [ -f "src/infrastructure/memory/working_memory_repository.py" ]; then
  rm src/infrastructure/memory/working_memory_repository.py
  echo "  DELETED: src/infrastructure/memory/working_memory_repository.py"
else
  echo "  OK: already deleted"
fi

echo ""
echo "=== Step 5: Verify no dead code references in tools/ ==="
DEAD_REFS=$(grep -rn 'UniversalDBAdapter\|postgres_database\|postgres_adapter\|async_postgres\|working_memory_repository\|WorkingMemoryRepository\|PostgreSQLDatabase\|PostgreSQLAdapter\|AsyncPostgresAdapter\|WorkingMemoryExtractor' tools/ 2>/dev/null || true)
if [ -z "$DEAD_REFS" ]; then
  echo "  OK: no dead code references in tools/"
else
  echo "  WARNING: dead code references found in tools/:"
  echo "$DEAD_REFS" | head -10
fi

echo ""
echo "=== Step 6: Check SQLite schema (new tables) ==="
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('data/memory.db')
cursor = conn.cursor()
tables = ['memory_links', 'user_preferences', 'memory_tags']
missing = []
for table in tables:
    cursor.execute(f\"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'\")
    if cursor.fetchone() is None:
        missing.append(table)
if missing:
    print(f'  MISSING tables: {missing}')
else:
    print('  OK: all new SQLite tables exist')
conn.close()
" 2>&1 || echo "  SKIP: data/memory.db not found (will be created on first run)"

echo ""
echo "=== Step 7: Check ChromaDB ==="
.venv/bin/python3 -c "
import chromadb
client = chromadb.PersistentClient(path='data/chroma')
collection = client.get_or_create_collection('memories')
print(f'  OK: ChromaDB collection exists, {collection.count()} vectors')
" 2>&1 || echo "  SKIP: data/chroma not found (will be created on first run)"

echo ""
echo "=== Step 8: Test py_compile on all src/ ==="
FAILS=0
for f in \$(find src/ -name '*.py' -not -path '*/__pycache__/*'); do
  if ! .venv/bin/python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
    echo "  FAIL: $f"
    FAILS=\$((FAILS + 1))
  fi
done
if [ "\$FAILS" -eq 0 ]; then
  echo "  OK: all src/*.py files compile"
else
  echo "  \$FAILS files failed to compile"
fi

echo ""
echo "=== All checks complete ==="
