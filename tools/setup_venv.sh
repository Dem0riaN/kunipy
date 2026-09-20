#!/bin/bash
set -e
cd /home/alexey/dev/kunipy

echo "=== 1. Create venv (python3.12) ==="
python3 -m venv .venv
.venv/bin/python --version

echo ""
echo "=== 2. Upgrade pip ==="
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip --version

echo ""
echo "=== 3. Install core deps needed for import checks (light) ==="
# chromadb pulls a lot; install incrementally to isolate failures
.venv/bin/pip install numpy "chromadb>=0.5.0" --quiet 2>&1 | tail -5

echo ""
echo "=== 4. Install dev tools (ruff, pytest) ==="
.venv/bin/pip install "ruff>=0.5.0" "pytest>=8.0.0" "pytest-asyncio>=0.23.0" httpx --quiet 2>&1 | tail -5

echo ""
echo "=== 5. Verify chromadb + ruff present ==="
.venv/bin/python -c "import chromadb; print('chromadb', chromadb.__version__)"
.venv/bin/ruff --version

echo ""
echo "=== DONE ==="
