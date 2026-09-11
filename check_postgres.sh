#!/bin/bash
# Quick PostgreSQL availability check for kunipy

set -e

echo "=== PostgreSQL Quick Check ==="
echo ""

# Check if PostgreSQL is installed
if command -v psql &> /dev/null; then
    echo "✓ PostgreSQL client installed"
    psql --version
else
    echo "✗ PostgreSQL not found"
    echo ""
    echo "Installing PostgreSQL..."
    sudo apt update
    sudo apt install -y postgresql postgresql-contrib
    echo "✓ PostgreSQL installed"
fi

echo ""

# Check if PostgreSQL service is running
if sudo systemctl is-active --quiet postgresql 2>/dev/null; then
    echo "✓ PostgreSQL service is running"
else
    echo "Starting PostgreSQL service..."
    sudo systemctl start postgresql
    sleep 2
    echo "✓ PostgreSQL service started"
fi

echo ""
echo "PostgreSQL Status:"
sudo systemctl status postgresql --no-pager -l | head -10

echo ""
echo "=== Setup Complete ==="
