#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

echo "=== Step 0: Copy ALL WIN-newer core files to WSL ==="
WIN_NEWER=(
  README.md
  config.example.toml
  docs/ARCHITECTURE.md
  docs/FINAL_REPORT.md
  docs/MIGRATION.md
  docs/deployment-summary-ru.md
  docs/memory-system-implementation-status.md
  src/config.py
  src/di/container.py
  src/infrastructure/memory/database.py
  src/infrastructure/memory/kuni_migrator.py
  src/infrastructure/memory/memory_repository.py
  src/infrastructure/memory/memory_service.py
  src/infrastructure/memory/storage.py
  src/infrastructure/memory/vector_store.py
  src/memory_integrated_worker.py
)
for f in "${WIN_NEWER[@]}"; do
  cp "/mnt/g/AI/kunipy-main/$f" "$f"
  echo "  COPIED: $f"
done

echo ""
echo "=== Step 1: Copy WIN-only new repos to WSL ==="
for f in memory_link_repository.py memory_tag_repository.py user_preference_repository.py; do
  cp "/mnt/g/AI/kunipy-main/src/infrastructure/memory/$f" "src/infrastructure/memory/$f"
  echo "  COPIED: src/infrastructure/memory/$f"
done

echo ""
echo "=== Step 2: Copy WIN-only test and doc files ==="
WIN_ONLY_FILES=(
  test_memory_minimal.py
  test_memory_integration.py
  test_memory_formation.py
  test_memory_worker_integration.py
  migrate_kuni.py
  export_memory.py
  CURRENT_STATE.md
  ANALYSIS_TZ002.md
)
for f in "${WIN_ONLY_FILES[@]}"; do
  if [ -f "/mnt/g/AI/kunipy-main/$f" ]; then
    cp "/mnt/g/AI/kunipy-main/$f" "$f"
    echo "  COPIED: $f"
  fi
done

echo ""
echo "=== Step 3: Delete PostgreSQL/dead files from WSL ==="
PG_DELETE=(
  src/infrastructure/memory/async_postgres_adapter.py
  src/infrastructure/memory/async_postgres_connection.py
  src/infrastructure/memory/postgres_adapter.py
  src/infrastructure/memory/postgres_database.py
  src/infrastructure/memory/universal_db_adapter.py
  src/infrastructure/memory/working_memory_extractor.py
)
for f in "${PG_DELETE[@]}"; do
  if [ -f "$f" ]; then
    rm "$f"
    echo "  DELETED: $f"
  fi
done

echo ""
echo "=== Step 4: Copy WIN memory/__init__.py (exports new repos) ==="
cp "/mnt/g/AI/kunipy-main/src/infrastructure/memory/__init__.py" "src/infrastructure/memory/__init__.py"
echo "  COPIED: src/infrastructure/memory/__init__.py"

echo ""
echo "=== Done. Remaining: merge container.py and memory_integrated_worker.py ==="
