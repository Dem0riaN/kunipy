#!/bin/bash
cd /home/alexey/dev/kunipy

echo "=== sync Windows changes to WSL ==="
# proxy_server.py + sleep_consolidation.py (both fixed) + pyproject.toml
for f in src/proxy_server.py src/infrastructure/memory/sleep_consolidation.py pyproject.toml; do
    WIN="/mnt/g/AI/kunipy-main/$f"
    if [ -f "$WIN" ]; then
        cp -f "$WIN" "$f"
        echo "  synced: $f"
    else
        echo "  MISSING on Windows: $WIN"
    fi
done

echo ""
echo "=== ruff check (critical rules only: F821, B023, ASYNC230, DTZ006) ==="
.venv/bin/ruff check src/ --select F821,B023,ASYNC230,DTZ006 -n 2>&1 | head -30

echo ""
echo "=== ruff statistics (all rules) ==="
.venv/bin/ruff check src/ --statistics 2>&1 | head -20

echo ""
echo "=== test runner discovery ==="
.venv/bin/python3 -m pytest --collect-only test_memory_minimal.py test_memory_integration.py test_memory_formation.py test_memory_worker_integration.py 2>&1 | tail -20

echo ""
echo "=== run memory tests ==="
.venv/bin/python3 -m pytest test_memory_minimal.py test_memory_formation.py -x -q --tb=short 2>&1 | tail -40
