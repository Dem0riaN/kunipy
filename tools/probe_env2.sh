#!/bin/bash
cd /home/alexey/dev/kunipy

echo "=== pip list (system) ==="
pip3 list 2>/dev/null | head -30

echo ""
echo "=== old deploy venv? ==="
ls -la /home/alexey/kunipy/.venv 2>/dev/null || echo "no .venv in /home/alexey/kunipy"
ls -la /home/alexey/kunipy/venv 2>/dev/null || echo "no venv in /home/alexey/kunipy"

echo ""
echo "=== check pyproject-managed env (uv/poetry) ==="
ls -la .python-version 2>/dev/null || echo "no .python-version"
ls -la /home/alexey/.cache/pypoetry/virtualenvs 2>/dev/null | head || echo "no poetry venvs"

echo ""
echo "=== venv module available? ==="
python3 -m venv --help >/dev/null 2>&1 && echo "venv module OK" || echo "venv module MISSING (need python3.12-venv)"

echo ""
echo "=== how did tests run before? check bash history ==="
grep -a 'source.*activate\|\.venv\|pytest\|test_memory' /home/alexey/.bash_history 2>/dev/null | tail -20
