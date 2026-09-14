#!/bin/bash
cd /home/alexey/dev/kunipy
echo "=== file existence checks ==="
for f in src/infrastructure/embedding_adapter.py src/infrastructure/memory/storage.py src/infrastructure/memory/vector_store.py src/infrastructure/memory/memory_service.py src/infrastructure/memory/memory_link_repository.py src/infrastructure/memory/memory_tag_repository.py src/infrastructure/memory/user_preference_repository.py; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done

echo ""
echo "=== AST parse of tools ==="
.venv/bin/python3 - <<'PY'
import ast
for p in ["tools/migrate_kuni.py", "tools/export_memory.py"]:
    try:
        ast.parse(open(p).read())
        print(f"OK: {p}")
    except Exception as e:
        print(f"FAIL: {p}: {e}")
PY

echo ""
echo "=== Import sanity on src ==="
.venv/bin/python3 - <<'PY'
try:
    from src.infrastructure.memory import (
        MemoryService, MemoryStore, WorkingMemory,
        MemoryLinkRepository, UserPreferenceRepository, MemoryTagRepository,
        DiaryContextInjector, SleepConsolidationService,
    )
    print("src memory imports OK")
except Exception as e:
    print(f"FAIL: {e}")

try:
    from src.di.container import create_dependencies, Dependencies
    print("DI container import OK")
except Exception as e:
    print(f"FAIL: {e}")

try:
    from src.config import load_config
    print("config import OK")
except Exception as e:
    print(f"FAIL: {e}")
PY

echo ""
echo "=== ruff on replaced tools ==="
.venv/bin/ruff check tools/export_memory.py tools/migrate_kuni.py 2>&1 | head -20

echo ""
echo "=== dead PG imports ==="
grep -rn 'postgres_database\|UniversalDBAdapter\|postgres_adapter\|async_postgres\|working_memory_repository' src/ tools/ --include='*.py' 2>/dev/null | grep -v '\.pyc\|egg-info' || echo "CLEAN"
