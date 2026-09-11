#!/bin/bash
# Memory System Deployment Verification Script
# Run this after deployment to verify all components are working

set -e

echo "=========================================="
echo "Memory System Deployment Verification"
echo "=========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "run.py" ]; then
    echo -e "${RED}✗ Error: run.py not found. Please run this script from the kunipy directory.${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found kunipy directory"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠ Virtual environment not activated. Activating...${NC}"
    source .venv/bin/activate
fi

echo -e "${GREEN}✓${NC} Virtual environment activated: $VIRTUAL_ENV"
echo ""

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Check if required files exist
echo ""
echo "Checking memory system files..."

FILES=(
    "src/domain/memory_models.py"
    "src/infrastructure/memory/database.py"
    "src/infrastructure/memory/conversation_repository.py"
    "src/infrastructure/memory/memory_repository.py"
    "src/infrastructure/memory/working_memory_repository.py"
    "src/infrastructure/memory/user_chat_repository.py"
    "src/infrastructure/memory/memory_service.py"
    "test_memory_minimal.py"
    "test_memory_integration.py"
)

ALL_FOUND=true
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file - NOT FOUND"
        ALL_FOUND=false
    fi
done

if [ "$ALL_FOUND" = false ]; then
    echo -e "${RED}✗ Some files are missing. Please check deployment.${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "Running Tests"
echo "=========================================="
echo ""

# Run minimal test
echo "Test 1: Repository Layer (test_memory_minimal.py)"
echo "---"
if python test_memory_minimal.py; then
    echo -e "${GREEN}✓ Minimal test passed${NC}"
else
    echo -e "${RED}✗ Minimal test failed${NC}"
    exit 1
fi

echo ""
echo "Test 2: Integration Test (test_memory_integration.py)"
echo "---"
if python test_memory_integration.py; then
    echo -e "${GREEN}✓ Integration test passed${NC}"
else
    echo -e "${RED}✗ Integration test failed${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "Checking Configuration"
echo "=========================================="
echo ""

if [ -f "config.toml" ]; then
    echo -e "${GREEN}✓${NC} config.toml exists"

    # Check for memory configuration
    if grep -q "memory_enabled" config.toml; then
        MEMORY_ENABLED=$(grep "memory_enabled" config.toml | awk '{print $3}')
        echo "  memory_enabled = $MEMORY_ENABLED"
    else
        echo -e "${YELLOW}⚠ memory_enabled not found in config.toml${NC}"
    fi

    if grep -q "memory_db_path" config.toml; then
        MEMORY_DB_PATH=$(grep "memory_db_path" config.toml | awk '{print $3}')
        echo "  memory_db_path = $MEMORY_DB_PATH"
    else
        echo -e "${YELLOW}⚠ memory_db_path not found in config.toml${NC}"
    fi
else
    echo -e "${YELLOW}⚠ config.toml not found - copy from config.example.toml${NC}"
fi

echo ""
echo "=========================================="
echo "Deployment Summary"
echo "=========================================="
echo ""
echo -e "${GREEN}✅ All memory system components verified successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Ensure config.toml has memory_enabled = true"
echo "2. Run the application: python run.py"
echo "3. Send test messages via Telegram to verify storage"
echo ""
echo "Documentation:"
echo "- docs/memory-system-implementation-status.md"
echo "- docs/deployment-summary-ru.md"
echo ""
echo "Known issue: TDLib may crash (exit code 139) - this is expected and deferred."
echo ""
