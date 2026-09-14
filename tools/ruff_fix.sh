#!/bin/bash
cd /home/alexey/dev/kunipy

echo "=== ruff before ==="
.venv/bin/ruff check src/ --statistics 2>/dev/null | head -20

echo ""
echo "=== apply safe fixes (src/) ==="
.venv/bin/ruff check src/ --fix 2>&1 | tail -5

echo ""
echo "=== apply safe fixes (tools/, root tests) ==="
.venv/bin/ruff check tools/ test_memory_*.py migrate_kuni.py export_memory.py --fix 2>&1 | tail -5

echo ""
echo "=== ruff after (statistics) ==="
.venv/bin/ruff check src/ tools/ test_memory_*.py migrate_kuni.py export_memory.py --statistics 2>/dev/null | head -30

echo ""
echo "=== sync ruff-fixed files back to Windows ==="
# Files that ruff auto-fixed differ now; copy back src/ and root tests
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='data' --exclude='diary' --exclude='.git' \
  --include='*.py' --include='*/' --exclude='*' \
  src/ /mnt/g/AI/kunipy-main/src/ 2>/dev/null || \
  cp -ru src/. /mnt/g/AI/kunipy-main/src/ 2>/dev/null

# root tests + tools
for f in test_memory_minimal.py test_memory_integration.py test_memory_formation.py test_memory_worker_integration.py migrate_kuni.py export_memory.py; do
  cp "$f" "/mnt/g/AI/kunipy-main/$f" 2>/dev/null && echo "  synced back: $f"
done

echo ""
echo "=== import sanity after fixes ==="
.venv/bin/python3 -c "
from src.infrastructure.memory import (
    MemoryService, MemoryStore, WorkingMemory,
    MemoryLinkRepository, UserPreferenceRepository, MemoryTagRepository,
    DiaryContextInjector, SleepConsolidationService,
)
from src.di.container import create_dependencies, Dependencies
print('imports OK after ruff --fix')
"
