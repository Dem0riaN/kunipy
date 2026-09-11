#!/bin/bash
# PostgreSQL setup script for kunipy memory system
# Run this in WSL Ubuntu-24.04

set -e

echo "=========================================="
echo "PostgreSQL Setup for kunipy Memory System"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo -e "${YELLOW}PostgreSQL not found. Installing...${NC}"
    sudo apt update
    sudo apt install -y postgresql postgresql-contrib
    echo -e "${GREEN}✓ PostgreSQL installed${NC}"
else
    echo -e "${GREEN}✓ PostgreSQL already installed${NC}"
fi

# Check if PostgreSQL is running
if ! sudo systemctl is-active --quiet postgresql; then
    echo -e "${YELLOW}Starting PostgreSQL...${NC}"
    sudo systemctl start postgresql
    echo -e "${GREEN}✓ PostgreSQL started${NC}"
else
    echo -e "${GREEN}✓ PostgreSQL is running${NC}"
fi

# Create database and user
echo ""
echo "Creating database and user..."

sudo -u postgres psql << EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'kunipy') THEN
        CREATE USER kunipy WITH PASSWORD 'kunipy';
    END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE kunipy OWNER kunipy'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'kunipy')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE kunipy TO kunipy;

\c kunipy

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO kunipy;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO kunipy;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO kunipy;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO kunipy;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO kunipy;
EOF

echo -e "${GREEN}✓ Database 'kunipy' and user 'kunipy' created${NC}"

# Test connection
echo ""
echo "Testing connection..."
if PGPASSWORD=kunipy psql -h localhost -U kunipy -d kunipy -c "SELECT version();" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Connection successful${NC}"
else
    echo -e "${RED}✗ Connection failed${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "PostgreSQL Setup Complete"
echo "=========================================="
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: kunipy"
echo "  User: kunipy"
echo "  Password: kunipy"
echo ""
echo "Connection string:"
echo "  postgresql://kunipy:kunipy@localhost:5432/kunipy"
echo ""
echo "Next steps:"
echo "1. Install psycopg: pip install 'psycopg[binary]>=3.1.0'"
echo "2. Update config.toml:"
echo "   memory_backend = \"postgresql\""
echo "   memory_postgres_url = \"postgresql://kunipy:kunipy@localhost:5432/kunipy\""
echo "3. Run application: python run.py"
echo ""
