#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

echo "=== Step 1: Copy WIN-newer files to WSL ==="
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
  src/infrastructure/memory/__init__.py
  src/infrastructure/memory/database.py
  src/infrastructure/memory/kuni_migrator.py
  src/infrastructure/memory/memory_repository.py
  src/infrastructure/memory/memory_service.py
  src/infrastructure/memory/storage.py
  src/infrastructure/memory/vector_store.py
)

for f in "${WIN_NEWER[@]}"; do
  cp "/mnt/g/AI/kunipy-main/$f" "$f"
  echo "  COPIED: $f"
done

echo ""
echo "=== Step 2: Copy new WIN-only files (new repos, tests, docs) to WSL ==="
WIN_ONLY=(
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
)

for f in "${WIN_ONLY[@]}"; do
  if [ -f "/mnt/g/AI/kunipy-main/$f" ]; then
    cp "/mnt/g/AI/kunipy-main/$f" "$f"
    echo "  COPIED (new): $f"
  else
    echo "  SKIP (not found): $f"
  fi
done

echo ""
echo "=== Step 3: Delete PostgreSQL/legacy files from WSL ==="
TO_DELETE=(
  src/infrastructure/memory/async_postgres_adapter.py
  src/infrastructure/memory/async_postgres_connection.py
  src/infrastructure/memory/postgres_adapter.py
  src/infrastructure/memory/postgres_database.py
  src/infrastructure/memory/universal_db_adapter.py
  src/infrastructure/memory/working_memory_extractor.py
  src/infrastructure/memory/working_memory_repository.py
  docs/POSTGRESQL_MIGRATION.md
  tools/setup_postgresql.sh
)

for f in "${TO_DELETE[@]}"; do
  if [ -f "$f" ]; then
    rm -f "$f"
    echo "  DELETED: $f"
  else
    echo "  SKIP (not found): $f"
  fi
done

echo ""
echo "=== Step 4: Verify sync ==="
echo "Checking for any remaining different files..."
DIFFERENT=0
while IFS= read -r f; do
    win="/mnt/g/AI/kunipy-main/${f#./}"
    [ -f "$win" ] || continue
    if ! cmp -s "$f" "$win"; then
        DIFFERENT=$((DIFFERENT + 1))
        echo "  STILL DIFFERENT: $f"
    fi
done < <(find . -type f \( -name '*.py' -o -name '*.toml' -o -name '*.md' \) \
    -not -path './.venv/*' -not -path '*/__pycache__/*' | sort)

echo "  Total still different: $DIFFERENT"

echo ""
echo "=== Sync complete ==="
