#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

echo "=== Step 1: Copy ALL modified Windows files to WSL ==="
MODIFIED_FILES=(
  src/di/container.py
  src/app.py
  src/worker.py
  src/memory_integrated_worker.py
  src/diary.py
  src/infrastructure/memory/__init__.py
)

for f in "${MODIFIED_FILES[@]}"; do
  cp "/mnt/g/AI/kunipy-main/$f" "$f"
  echo "  SYNCED: $f"
done

echo ""
echo "=== Step 2: py_compile check ==="
FAILS=0
for f in $(find src/ -name '*.py' -not -path './.venv/*' -not -path '*/__pycache__/*'); do
  if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
    echo "  FAIL: $f"
    FAILS=$((FAILS + 1))
  fi
done
if [ "$FAILS" -eq 0 ]; then
  echo "  OK: all .py files compile"
else
  echo "  $FAILS files failed to compile"
fi

echo ""
echo "=== Step 3: Import check ==="
source .venv/bin/activate 2>/dev/null || true
python3 -c "
from src.infrastructure.memory import (
    MemoryService, MemoryStore, WorkingMemory,
    MemoryLinkRepository, UserPreferenceRepository, MemoryTagRepository,
    DiaryContextInjector, SleepConsolidationService,
    ConversationRepository, MemoryRepository, MemoryDatabase,
    UserRepository, ChatRepository, DiaryDumpService,
)
print('  OK: all imports successful')
" 2>&1 || echo "  FAIL: import error"

echo ""
echo "=== Step 4: Dead code check ==="
DEAD_REFS=$(grep -rn 'UniversalDBAdapter\|postgres_database\|postgres_adapter\|async_postgres\|working_memory_repository\|working_memory_extractor' src/ --include='*.py' 2>/dev/null || true)
if [ -z "$DEAD_REFS" ]; then
  echo "  OK: no references to deleted modules"
else
  echo "  WARNING: dead code references found:"
  echo "$DEAD_REFS"
fi

echo ""
echo "=== Step 5: New repos exist ==="
for repo in memory_link_repository.py memory_tag_repository.py user_preference_repository.py; do
  if [ -f "src/infrastructure/memory/$repo" ]; then
    echo "  OK: $repo"
  else
    echo "  MISSING: $repo"
  fi
done

echo ""
echo "=== Step 6: Phase 2/4 wiring in container.py ==="
for pattern in "diary_context_injector" "consolidation_service" "DiaryContextInjector" "SleepConsolidationService" "set_consolidation_service"; do
  count=$(grep -c "$pattern" src/di/container.py 2>/dev/null || echo 0)
  echo "  container.py has '$pattern': $count refs"
done

echo ""
echo "=== Step 7: Phase 2/4 wiring in app.py ==="
for pattern in "diary_context_injector"; do
  count=$(grep -c "$pattern" src/app.py 2>/dev/null || echo 0)
  echo "  app.py has '$pattern': $count refs"
done

echo ""
echo "=== Step 8: Diary Phase 2 methods ==="
for method in "delete_entry" "get_all_entries" "set_consolidation_service" "sleep_consolidation"; do
  if grep -q "def $method" src/diary.py; then
    echo "  OK: diary.py has $method()"
  else
    echo "  MISSING: diary.py $method()"
  fi
done

echo ""
echo "=== Step 9: MemoryIntegratedWorker Phase 4 ==="
for pattern in "_diary_context_injector" "legacy_diary" "combined_diary" "inject_into_system_prompt"; do
  count=$(grep -c "$pattern" src/memory_integrated_worker.py 2>/dev/null || echo 0)
  echo "  memory_integrated_worker.py has '$pattern': $count refs"
done

echo ""
echo "=== Step 10: Worker Phase 4 message injection ==="
count=$(grep -c "inject_into_messages" src/worker.py 2>/dev/null || echo 0)
echo "  worker.py has 'inject_into_messages': $count refs"

echo ""
echo "=== All checks complete ==="
