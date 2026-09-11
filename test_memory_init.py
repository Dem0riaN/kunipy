"""Test memory system initialization."""

import asyncio
from pathlib import Path

from src.config import load_config
from src.di.container import create_dependencies


async def main():
    """Test memory system initialization."""
    try:
        config = load_config("config.toml")
        print(f"✓ Config loaded")
        print(f"  memory_enabled: {config.memory_enabled}")
        print(f"  memory_db_path: {config.memory_db_path}")
        print(f"  memory_min_similarity: {config.memory_min_similarity}")

        deps = await create_dependencies(Path("data"), config)
        print(f"✓ Dependencies created")
        print(f"  memory_service: {deps.memory_service}")

        if deps.memory_service:
            print(f"✓ MemoryService initialized successfully")
            return True
        else:
            print(f"⚠ MemoryService not initialized (memory_enabled={config.memory_enabled})")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
