#!/usr/bin/env python3
"""Автоматическая миграция diary из C++ kuni в kunipy.

Usage:
    python migrate_diary.py --kuni-dir /path/to/kuni/diary
    python migrate_diary.py --kuni-dir /path/to/kuni/diary --output-dir ./data/migrated
    python migrate_diary.py --kuni-dir /path/to/kuni/diary --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

from src.config import load_config
from src.infrastructure.memory import MemoryStore
from src.openai_chat import OpenAIChat
from src.tools.migrate_legacy_diary import LegacyDiaryMigrator


async def main():
    parser = argparse.ArgumentParser(
        description="Миграция diary из C++ kuni в kunipy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  Базовая миграция:
    python migrate_diary.py --kuni-dir D:/kuni/diary

  С custom output директорией:
    python migrate_diary.py --kuni-dir D:/kuni/diary --output-dir ./data/custom

  Dry-run (проверка без записи):
    python migrate_diary.py --kuni-dir D:/kuni/diary --dry-run

  С custom конфигом:
    python migrate_diary.py --kuni-dir D:/kuni/diary --config custom_config.toml

Формат C++ kuni diary:
  Файлы: YYYY-MM-DD_HH-MM-SS_*.txt
  Содержимое:
    # KUNI DIARY
    confidence: 0.85
    importance: 0.7
    user_id: 123456789
    chat_id: 987654321
    ---
    Текст записи памяти...
        """,
    )

    parser.add_argument(
        "--kuni-dir",
        type=Path,
        required=True,
        help="Путь к директории diary из C++ kuni (содержит *.txt файлы)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Директория для ChromaDB (default: ./data/chroma из config.toml)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Путь к config.toml (default: ./config.toml)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Проверить файлы без фактической миграции",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод (показывать каждый файл)",
    )

    args = parser.parse_args()

    # Validation
    if not args.kuni_dir.exists():
        print(f"❌ Ошибка: Директория не существует: {args.kuni_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.kuni_dir.is_dir():
        print(f"❌ Ошибка: Путь не является директорией: {args.kuni_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.config.exists():
        print(f"❌ Ошибка: Config файл не найден: {args.config}", file=sys.stderr)
        print("   Создайте config.toml или укажите --config путь", file=sys.stderr)
        sys.exit(1)

    # Load configuration
    print(f"📋 Загрузка конфигурации: {args.config}")
    try:
        config = load_config(str(args.config))
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"❌ Ошибка загрузки конфига: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup embedding provider
    print("🔧 Инициализация embedding provider...")
    embedding_provider = OpenAIChat(
        api_key=config.llm.endpoint.bearer_key,
        base_url=config.llm.endpoint.base_url,
        default_model=config.llm.model,
    )

    # Setup output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # Use diary_dir from config as base
        output_dir = Path(config.diary_dir) / "chroma"

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output директория: {output_dir}")

    # Initialize memory store
    if not args.dry_run:
        print("🗄️  Инициализация ChromaDB...")
        memory_store = MemoryStore(persist_directory=str(output_dir))

    # Initialize migrator
    print(f"🔍 Сканирование C++ kuni diary: {args.kuni_dir}")
    migrator = LegacyDiaryMigrator(
        kuni_diary_dir=args.kuni_dir,
        embedding_provider=embedding_provider,
    )

    # Count files
    diary_files = list(args.kuni_dir.glob("*.txt"))
    if not diary_files:
        print(f"⚠️  Предупреждение: Не найдено *.txt файлов в {args.kuni_dir}")
        print("   Убедитесь что путь указывает на diary директорию C++ kuni")
        sys.exit(0)

    print(f"📊 Найдено файлов для миграции: {len(diary_files)}")

    if args.dry_run:
        print("\n🔍 DRY-RUN режим: проверка без записи\n")
        # Parse and show stats without migration
        valid_count = 0
        invalid_count = 0

        for diary_file in diary_files:
            try:
                entry = migrator.parse_diary_file(diary_file)
                valid_count += 1
                if args.verbose:
                    print(f"  ✅ {diary_file.name}")
                    print(f"     User: {entry.user_id}, Chat: {entry.chat_id}")
                    print(f"     Confidence: {entry.confidence}, Importance: {entry.importance}")
                    print(f"     Content: {len(entry.content)} chars")
            except (ValueError, KeyError, FileNotFoundError) as e:
                invalid_count += 1
                if args.verbose:
                    print(f"  ❌ {diary_file.name}: {e}")

        print("\n📊 Результаты проверки:")
        print(f"   ✅ Валидных файлов: {valid_count}")
        print(f"   ❌ Невалидных файлов: {invalid_count}")
        print("\n✨ Dry-run завершён. Для миграции запустите без --dry-run")
        sys.exit(0)

    # Actual migration
    print("\n🚀 Начало миграции...\n")

    try:
        migrated_entries = await migrator.migrate_all(
            target_store=memory_store,
            show_progress=True,
        )

        print("\n✅ Миграция завершена успешно!")
        print(f"   Мигрировано записей: {len(migrated_entries)}")
        print(f"   ChromaDB location: {output_dir}")
        print("\n💡 Для использования обновите config.toml:")
        print("   [diary]")
        print(f"   directory = \"{output_dir}\"")

    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as e:
        print(f"\n❌ Ошибка миграции: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
