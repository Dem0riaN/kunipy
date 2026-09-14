#!/bin/bash
cd /home/alexey/dev/kunipy

echo "=== Install project deps via pyproject.toml ==="
.venv/bin/pip install -e . 2>&1 | tail -20

echo ""
echo "=== Verify core imports ==="
.venv/bin/python3 -c "
import tomli
import chromadb
import numpy
print('tomli, chromadb, numpy — OK')
from src.infrastructure.memory import (
    MemoryService, MemoryStore, WorkingMemory,
    MemoryLinkRepository, UserPreferenceRepository, MemoryTagRepository,
    DiaryContextInjector, SleepConsolidationService,
    ConversationRepository, MemoryRepository, MemoryDatabase,
    UserRepository, ChatRepository, DiaryDumpService,
)
print('All memory infrastructure imports — OK')
from src.di.container import create_dependencies, Dependencies
print('DI container — OK')
from src.config import Config, load_config
print('Config — OK')
print('SUCCESS: all imports passed')
"
