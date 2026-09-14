#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

echo "=== Step 1: Copy WIN-only files to WSL (new repos, tests, docs) ==="
WIN_ONLY_FILES=(
  src/infrastructure/memory/memory_link_repository.py
  src/infrastructure/memory/memory_tag_repository.py
  src/infrastructure/memory/user_preference_repository.py
  test_memory_minimal.py
  test_memory_integration.py
  test_memory_formation.py
  test_memory_worker_integration.py
  migrate_kuni.py
  export_memory.py
  CURRENT_STATE.md
  ANALYSIS_TZ002.md
  BUGFIX_2026-09-12.md
  BUGFIX_2026-09-12_FINAL.md
  BUGFIX_2026-09-12_UPDATE2.md
  BUGFIX_2026-09-12_UPDATE4.md
  FINAL_STATUS_TZ002.md
  PROGRESS_TZ002_CRITICAL.md
  PROGRESS_TZ002_RUNTIME.md
)

for f in "${WIN_ONLY_FILES[@]}"; do
  if [ -f "/mnt/g/AI/kunipy-main/$f" ]; then
    # Ensure parent dir exists
    mkdir -p "$(dirname "$f")"
    cp "/mnt/g/AI/kunipy-main/$f" "$f"
    echo "  COPIED: $f"
  else
    echo "  SKIP (not found on WIN): $f"
  fi
done

echo ""
echo "=== Step 2: Keep WSL-newer files (preserve Phase 4 diary features) ==="
WSL_KEEP=(
  src/app.py
  src/diary.py
  src/proxy_server.py
  src/worker.py
  src/di/container.py
  src/memory_integrated_worker.py
)

for f in "${WSL_KEEP[@]}"; do
  if [ -f "$f" ]; then
    echo "  KEPT (WSL-newer): $f"
  fi
done

echo ""
echo "=== Step 3: Delete PostgreSQL files from WSL ==="
PG_DELETE=(
  src/infrastructure/memory/async_postgres_adapter.py
  src/infrastructure/memory/async_postgres_connection.py
  src/infrastructure/memory/postgres_adapter.py
  src/infrastructure/memory/postgres_database.py
  src/infrastructure/memory/universal_db_adapter.py
  docs/POSTGRESQL_MIGRATION.md
  tools/setup_postgresql.sh
)

for f in "${PG_DELETE[@]}"; do
  if [ -f "$f" ]; then
    rm -f "$f"
    echo "  DELETED: $f"
  else
    echo "  SKIP (not found): $f"
  fi
done

# KEEP working_memory_repository.py and working_memory_extractor.py
# because WSL container.py still imports WorkingMemoryRepository
echo ""
echo "=== Step 4: Verify final state ==="
echo "Checking file counts..."
WSL_PY=$(find . -name '*.py' -not -path './.venv/*' -not -path '*/__pycache__/*' | wc -l)
WIN_PY=$(find /mnt/g/AI/kunipy-main -name '*.py' -not -path '*/.venv/*' -not -path '*/__pycache__/*' | wc -l)
echo "  WSL .py files: $WSL_PY"
echo "  WIN .py files: $WIN_PY"

echo ""
echo "Checking new repos exist in WSL..."
for repo in memory_link_repository.py memory_tag_repository.py user_preference_repository.py; do
  if [ -f "src/infrastructure/memory/$repo" ]; then
    echo "  OK: src/infrastructure/memory/$repo"
  else
    echo "  MISSING: src/infrastructure/memory/$repo"
  fi
done

echo ""
echo "Checking PostgreSQL files removed from WSL..."
for pg in async_postgres_adapter.py async_postgres_connection.py postgres_adapter.py postgres_database.py universal_db_adapter.py; do
  if [ -f "src/infrastructure/memory/$pg" ]; then
    echo "  STILL EXISTS: src/infrastructure/memory/$pg"
  else
    echo "  OK (deleted): src/infrastructure/memory/$pg"
  fi
done

echo ""
echo "=== Sync complete ==="
