#!/bin/bash
echo "=== Phase 2/4 service files — WSL ==="
cd /home/alexey/dev/kunipy
for f in sleep_consolidation diary_context_injector diary_dump diary_vector_store diary_file_store token_counter; do
  found=$(ls src/infrastructure/memory/${f}*.py 2>/dev/null)
  if [ -n "$found" ]; then
    echo "  OK  $found"
  else
    echo "  MISSING $f"
  fi
done

echo ""
echo "=== Phase 2/4 service files — WINDOWS ==="
cd /mnt/g/AI/kunipy-main
for f in sleep_consolidation diary_context_injector diary_dump diary_vector_store diary_file_store token_counter; do
  found=$(ls src/infrastructure/memory/${f}*.py 2>/dev/null)
  if [ -n "$found" ]; then
    echo "  OK  $found"
  else
    echo "  MISSING $f"
  fi
done

echo ""
echo "=== All WSL memory/ python files ==="
cd /home/alexey/dev/kunipy
ls -1 src/infrastructure/memory/*.py | sort

echo ""
echo "=== All WIN memory/ python files ==="
cd /mnt/g/AI/kunipy-main
ls -1 src/infrastructure/memory/*.py | sort
