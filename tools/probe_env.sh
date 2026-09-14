#!/bin/bash
cd /home/alexey/dev/kunipy

echo "=== uv available? ==="
if command -v uv >/dev/null 2>&1; then
  echo "uv found: $(uv --version)"
else
  echo "uv NOT found"
fi

echo ""
echo "=== python versions ==="
python3 --version 2>&1
for v in 3.11 3.12 3.13; do
  command -v python$v >/dev/null 2>&1 && echo "python$v: $(python$v --version 2>&1)"
done

echo ""
echo "=== any site-packages with chromadb anywhere? ==="
find /home/alexey -name 'chromadb' -type d 2>/dev/null | grep -i 'site-packages' | head

echo ""
echo "=== uv python list ==="
command -v uv >/dev/null 2>&1 && uv python list 2>&1 | head
