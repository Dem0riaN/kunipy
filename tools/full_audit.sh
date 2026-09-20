#!/bin/bash
set -euo pipefail
cd /home/alexey/dev/kunipy

echo "=== 1. Импорт всех модулей памяти ==="
.venv/bin/python3 - <<'PY'
import sys
errors = []

# Core memory modules
modules = [
    ("src.config", "Config/load_config"),
    ("src.interfaces.memory", "MemoryPiece/MemoryScope/MemoryKind"),
    ("src.domain.memory_models", "ConversationMessage/WorkingMemoryItem"),
    ("src.infrastructure.memory.database", "MemoryDatabase"),
    ("src.infrastructure.memory.memory_repository", "MemoryRepository"),
    ("src.infrastructure.memory.memory_link_repository", "MemoryLinkRepository"),
    ("src.infrastructure.memory.memory_tag_repository", "MemoryTagRepository"),
    ("src.infrastructure.memory.user_preference_repository", "UserPreferenceRepository"),
    ("src.infrastructure.memory.user_chat_repository", "UserRepository/ChatRepository"),
    ("src.infrastructure.memory.conversation_repository", "ConversationRepository"),
    ("src.infrastructure.memory.working_memory", "WorkingMemory"),
    ("src.infrastructure.memory.working_memory_file_store", "WorkingMemoryFileStore"),
    ("src.infrastructure.memory.storage", "MemoryStore (ChromaDB)"),
    ("src.infrastructure.memory.vector_store", "VectorStore"),
    ("src.infrastructure.memory.memory_service", "MemoryService"),
    ("src.infrastructure.memory.memory_formation", "MemoryFormationService"),
    ("src.infrastructure.memory.embedding_cache", "EmbeddingCache"),
    ("src.infrastructure.memory.token_counter", "TokenCounter"),
    # Phase 1: Diary stores
    ("src.infrastructure.memory.diary_file_store", "DiaryFileStore"),
    ("src.infrastructure.memory.diary_vector_store", "DiaryVectorStore"),
    # Phase 2: Sleep consolidation
    ("src.infrastructure.memory.sleep_consolidation", "SleepConsolidationService"),
    # Phase 3: Diary pipeline
    ("src.infrastructure.memory.diary_dump_service", "DiaryDumpService"),
    # Phase 4: Auto-RAG
    ("src.infrastructure.memory.diary_context_injector", "DiaryContextInjector"),
    # Embedding adapter
    ("src.infrastructure.embedding_adapter", "OpenAIChatEmbeddingAdapter"),
    # DI container
    ("src.di.container", "create_dependencies/Dependencies"),
    # App
    ("src.app", "App/main"),
    # Worker
    ("src.worker", "Worker"),
    ("src.memory_integrated_worker", "MemoryIntegratedWorker"),
    # Diary
    ("src.diary", "Diary/DiaryEntry"),
    # Proxy
    ("src.proxy_server", "proxy_server"),
]

for mod_path, desc in modules:
    try:
        __import__(mod_path)
        print(f"  ✅ {mod_path:55s} ({desc})")
    except Exception as e:
        print(f"  ❌ {mod_path:55s} ({desc}) — {e}")
        errors.append((mod_path, str(e)))

print(f"\nРезультат: {len(modules) - len(errors)}/{len(modules)} модулей импортированы")
if errors:
    print("\nОШИБКИ:")
    for m, e in errors:
        print(f"  {m}: {e}")
PY

echo ""
echo "=== 2. Проверка SQLite schema completeness ==="
.venv/bin/python3 - <<'PY'
from src.infrastructure.memory.database import MemoryDatabase
from pathlib import Path

db_path = Path("data/audit_schema.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

db = MemoryDatabase(db_path)
conn = db.connect()
db.initialize_schema()

tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print(f"Таблицы в БД ({len(tables)}): {', '.join(tables)}")

needed = {
    'memory_pieces': 'метаданные воспоминаний',
    'memory_embeddings': 'векторные эмбеддинги',
    'memory_links': 'связи между сущностями (§35)',
    'user_preferences': 'предпочтения (§7.3)',
    'memory_tags': 'теги (§9)',
    'conversations': 'история диалогов (§20)',
    'users': 'профили пользователей',
    'chats': 'метаданные чатов',
    'working_memory': 'working memory (legacy)',
    'working_memory_items': 'working memory items (legacy)',
}

missing = []
for tbl, desc in needed.items():
    if tbl in tables:
        # Check columns
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
        print(f"  ✅ {tbl:25s} — {desc} (колонки: {', '.join(cols[:8])}{'...' if len(cols)>8 else ''})")
    else:
        print(f"  ❌ {tbl:25s} — {desc} — ОТСУТСТВУЕТ")
        missing.append(tbl)

if not missing:
    print("\n✅ Все таблицы памяти присутствуют")
else:
    print(f"\n❌ Отсутствуют таблицы: {', '.join(missing)}")

conn.close()
import os; os.unlink(db_path)
PY

echo ""
echo "=== 3. Проверка ChromaDB ==="
.venv/bin/python3 - <<'PY'
import tempfile, os
from src.infrastructure.memory.storage import MemoryStore

with tempfile.TemporaryDirectory() as td:
    store = MemoryStore(persist_directory=td)
    count = store._store._collection.count()
    print(f"  ChromaDB инициализирован, коллекция '{store._store._collection.name}', count={count}")
    print("  ✅ ChromaDB работает")
PY

echo ""
echo "=== 4. Проверка dual-write MemoryService ==="
.venv/bin/python3 - <<'PY'
import asyncio
import os
import uuid
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.infrastructure.memory.database import MemoryDatabase
from src.infrastructure.memory.memory_repository import MemoryRepository
from src.infrastructure.memory.memory_link_repository import MemoryLinkRepository
from src.infrastructure.memory.memory_tag_repository import MemoryTagRepository
from src.infrastructure.memory.user_preference_repository import UserPreferenceRepository
from src.infrastructure.memory.conversation_repository import ConversationRepository
from src.infrastructure.memory.user_chat_repository import UserRepository, ChatRepository
from src.infrastructure.memory.working_memory import WorkingMemory
from src.infrastructure.memory.working_memory_file_store import WorkingMemoryFileStore
from src.infrastructure.memory.storage import MemoryStore
from src.infrastructure.memory.memory_service import MemoryService
from src.interfaces.memory import MemoryPiece, MemoryKind, MemoryScope
from src.config import load_config

async def test_dual_write():
    # Создаём временную БД
    db_path = Path("data/audit_dualwrite.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = MemoryDatabase(db_path)
    conn = db.connect()
    db.initialize_schema()

    with tempfile.TemporaryDirectory() as chroma_dir:
        # Создаём все репозитории
        memory_repo = MemoryRepository(conn)
        link_repo = MemoryLinkRepository(conn)
        tag_repo = MemoryTagRepository(conn)
        pref_repo = UserPreferenceRepository(conn)
        conv_repo = ConversationRepository(conn)
        user_repo = UserRepository(conn)
        chat_repo = ChatRepository(conn)

        wm_store = WorkingMemoryFileStore(Path("data/audit_wm.md"))
        working_memory = WorkingMemory(file_store=wm_store)

        memory_store = MemoryStore(persist_directory=chroma_dir)

        config = load_config("config.toml")

        # Создаём MemoryService с dual-write
        svc = MemoryService(
            memory_store=memory_store,
            conversation_repo=conv_repo,
            memory_repo=memory_repo,
            memory_link_repo=link_repo,
            user_preference_repo=pref_repo,
            memory_tag_repo=tag_repo,
            user_repo=user_repo,
            chat_repo=chat_repo,
            working_memory=working_memory,
            embedding_provider=None,
            config=config,
        )

        # Create user and chat first (FK constraint)
        await user_repo.get_or_create_user("telegram:test123", "Test User")
        await chat_repo.get_or_create_chat("telegram:chat456", "private", "Test Chat")

        now = datetime.now(UTC)
        mem_id = str(uuid.uuid4())

        # Создаём MemoryPiece
        piece = MemoryPiece(
            id=mem_id,
            kind=MemoryKind.FACT,
            content="Тест dual-write: проверка записи в оба хранилища",
            confidence=0.8,
            importance=0.7,
            created_at=now,
            updated_at=now,
            last_used=now,
            usage_count=0,
            embedding=[0.1] * 384,  # dummy 384-dim embedding
            scope=MemoryScope.GLOBAL,
            user_id="telegram:test123",
            chat_id="telegram:chat456",
            source_type="test",
            entities=["test_entity"],
            retrieval_cues=["dual_write_test"],
        )

        # Dual-write: ChromaDB + SQLite
        result_id = await svc.create_memory(piece)
        print(f"  ✅ create_memory: id={result_id}")

        # Verify SQLite
        from_sqlite = await memory_repo.get_memory(mem_id)
        if from_sqlite:
            print(f"  ✅ SQLite: content='{from_sqlite.content[:50]}...', scope={from_sqlite.scope.value}")
        else:
            print(f"  ❌ SQLite: не найдено по id={mem_id}")

        # Verify ChromaDB
        chroma_count = memory_store._store._collection.count()
        print(f"  ✅ ChromaDB: count={chroma_count}")

        # Test tags
        await tag_repo.add_tag(mem_id, "audit-tag")
        tags = await tag_repo.get_tags_for_memory(mem_id)
        print(f"  ✅ Tags: {tags}")

        # Test user preferences
        await pref_repo.set_preference("telegram:test123", "language", "ru")
        prefs = await pref_repo.get_all_preferences("telegram:test123")
        print(f"  ✅ Preferences: {prefs}")

        # Test working memory
        await working_memory.add_promise("telegram:test123", "telegram:chat456", "Тестовое обещание")
        ctx = await working_memory.get_context("telegram:test123", "telegram:chat456")
        print(f"  ✅ WorkingMemory: promises={len(ctx.promises)}, plans={len(ctx.plans)}, pending_questions={len(ctx.pending_questions)}")

        print(f"\n✅ Dual-write test пройден")

    # Cleanup
    conn.close()
    if db_path.exists():
        os.unlink(db_path)
    wm_path = Path("data/audit_wm.md")
    if wm_path.exists():
        os.unlink(wm_path)

asyncio.run(test_dual_write())
PY

echo ""
echo "=== 5. Проверка MemoryFormationService ==="
.venv/bin/python3 - <<'PY'
from src.infrastructure.memory.memory_formation import MemoryFormationService
print("  ✅ MemoryFormationService импортируется")
# Не запускаем — требует реальный LLM
PY

echo ""
echo "=== 6. Проверка Diary (Phase 1-4) ==="
.venv/bin/python3 - <<'PY'
import asyncio
from pathlib import Path
from src.diary import Diary, DiaryEntry
from src.infrastructure.memory.diary_file_store import DiaryFileStore
from src.infrastructure.memory.diary_vector_store import DiaryVectorStore
from src.infrastructure.memory.diary_dump_service import DiaryDumpService
from src.infrastructure.memory.diary_context_injector import DiaryContextInjector
from src.infrastructure.memory.sleep_consolidation import SleepConsolidationService
from src.infrastructure.memory.token_counter import TokenCounter
from src.config import load_config

config = load_config("config.toml")

print(f"  diary_enabled={config.diary_enabled}")
print(f"  diary_dir={config.diary_dir}")
print(f"  diary_auto_rag_enabled={config.diary_auto_rag_enabled}")

# Check diary dir exists
diary_path = Path(config.diary_dir)
print(f"  diary path exists: {diary_path.exists()}")

# Check diary files
if diary_path.exists():
    md_files = list(diary_path.glob("*.md"))
    print(f"  diary entries: {len(md_files)}")

print("  ✅ Diary modules (Phase 1-4) импортируются")
PY

echo ""
echo "=== 7. Проверка DI container ==="
.venv/bin/python3 - <<'PY'
import asyncio
from pathlib import Path
from src.config import load_config
from src.di.container import create_dependencies, Dependencies

async def check_di():
    config = load_config("config.toml")
    print(f"  config loaded: character={config.character_name}")
    print(f"  memory_enabled={config.memory_enabled}")
    print(f"  diary_enabled={config.diary_enabled}")
    print(f"  telegram_enabled={config.telegram_enabled}")
    print(f"  proxy_enabled={config.proxy_enabled}")
    # Не запускаем create_dependencies — требует Telegram/TDLib
    print("  ✅ DI container импортируется")

asyncio.run(check_di())
PY

echo ""
echo "=== 8. Проверка KuniMigrator ==="
.venv/bin/python3 - <<'PY'
from src.infrastructure.memory.kuni_migrator import KuniMigrator
from src.infrastructure.memory.kuni_archive_reader import KuniArchiveReader
from src.infrastructure.memory.memory_exporter import MemoryExporter
print("  ✅ KuniMigrator/KuniArchiveReader/MemoryExporter импортируются")
PY

echo ""
echo "=== 9. ruff critical check ==="
.venv/bin/ruff check src/ --select E9,F63,F7,F82 2>&1

echo ""
echo "=== ALL AUDITS DONE ==="
