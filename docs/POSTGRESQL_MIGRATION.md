# Миграция на PostgreSQL

## Обзор

Система памяти kunipy теперь поддерживает PostgreSQL в качестве backend для хранения данных. PostgreSQL рекомендуется для производственного использования при больших объемах воспоминаний, так как обеспечивает лучшую производительность и масштабируемость по сравнению с SQLite.

## Настройка PostgreSQL

### 1. Установка PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
```

**Windows (WSL):**
```bash
# В WSL Ubuntu-24.04
sudo apt update
sudo apt install -y postgresql postgresql-contrib
```

### 2. Настройка базы данных

```bash
# Запуск PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Создание пользователя и базы данных
sudo -u postgres psql << EOF
CREATE USER kunipy WITH PASSWORD 'kunipy';
CREATE DATABASE kunipy OWNER kunipy;
GRANT ALL PRIVILEGES ON DATABASE kunipy TO kunipy;
\c kunipy
GRANT ALL ON SCHEMA public TO kunipy;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO kunipy;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO kunipy;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO kunipy;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO kunipy;
\q
EOF
```

### 3. Проверка подключения

```bash
PGPASSWORD=kunipy psql -h localhost -U kunipy -d kunipy -c "SELECT version();"
```

## Конфигурация

### Переменные окружения

Добавьте в `.env`:

```env
# Memory system backend: sqlite or postgresql
MEMORY_BACKEND=postgresql

# PostgreSQL connection string (if using postgresql backend)
MEMORY_POSTGRES_URL=postgresql://kunipy:kunipy@localhost:5432/kunipy
```

### Пример конфигурации

**SQLite (по умолчанию):**
```env
MEMORY_BACKEND=sqlite
MEMORY_DB_PATH=data/memory.db
```

**PostgreSQL (рекомендуется для production):**
```env
MEMORY_BACKEND=postgresql
MEMORY_POSTGRES_URL=postgresql://kunipy:kunipy@localhost:5432/kunipy
```

## Миграция данных из SQLite в PostgreSQL

### Автоматическая миграция

Используйте скрипт `migrate_to_postgres.py`:

```bash
source .venv/bin/activate
python migrate_to_postgres.py data/memory.db postgresql://kunipy:kunipy@localhost:5432/kunipy
```

Скрипт:
- Проверяет существование исходной базы SQLite
- Подключается к обеим базам данных
- Копирует все таблицы с учетом зависимостей
- Конвертирует типы данных (JSON, datetime и т.д.)
- Использует `ON CONFLICT DO NOTHING` для безопасности

### Таблицы, которые мигрируются

1. `users` - пользователи
2. `chats` - чаты
3. `conversations` - история сообщений
4. `memories` - долговременная память
5. `memory_embeddings` - векторные представления
6. `working_memory` - рабочая память
7. `working_memory_items` - элементы рабочей памяти
8. `memory_links` - связи между воспоминаниями
9. `memory_tags` - теги воспоминаний
10. `user_preferences` - настройки пользователей

## Тестирование

### Запуск тестов PostgreSQL

```bash
source .venv/bin/activate
python test_postgres.py
```

Тест проверяет:
- ✅ Подключение к PostgreSQL
- ✅ Инициализацию схемы
- ✅ Создание пользователей и чатов
- ✅ Сохранение и получение сообщений
- ✅ Работу с рабочей памятью (promises, todos, context)

### Запуск приложения

```bash
source .venv/bin/activate
python run.py
```

## Архитектура

### Универсальный адаптер

Система использует `UniversalDBAdapter` для обеспечения совместимости между SQLite и PostgreSQL:

```python
from src.infrastructure.memory.universal_db_adapter import UniversalDBAdapter

# Автоматически определяет тип подключения
conn = UniversalDBAdapter(db_connection)

# Работает одинаково для обоих backend'ов
cursor = conn.cursor()
cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
```

### Конверсия типов данных

Адаптер автоматически конвертирует:

| SQLite | PostgreSQL | Конверсия |
|--------|------------|-----------|
| TEXT (JSON) | JSONB | `json.dumps()` / `json.loads()` |
| TEXT (datetime) | TIMESTAMPTZ | `.isoformat()` / `fromisoformat()` |
| `?` placeholder | `%s` placeholder | Автоматическая замена |

### Схема PostgreSQL

Основные отличия от SQLite:

1. **AUTO INCREMENT**:
   - SQLite: `INTEGER PRIMARY KEY AUTOINCREMENT`
   - PostgreSQL: `SERIAL PRIMARY KEY`

2. **JSON**:
   - SQLite: `TEXT` (хранится как строка)
   - PostgreSQL: `JSONB` (нативный тип)

3. **Datetime**:
   - SQLite: `TEXT` (ISO 8601 строка)
   - PostgreSQL: `TIMESTAMPTZ` (timestamp with timezone)

4. **Arrays**:
   - SQLite: `TEXT` (JSON array)
   - PostgreSQL: `REAL[]` (нативный массив)

## Производительность

### Рекомендации по объему данных

- **SQLite**: до 10,000 воспоминаний
- **PostgreSQL**: 10,000+ воспоминаний

### Оптимизации PostgreSQL

1. **Индексы**: Автоматически создаются для частых запросов
2. **JSONB**: Быстрые запросы по JSON полям
3. **Connection pooling**: Используется psycopg3 с автокоммитом

## Устранение проблем

### PostgreSQL не запускается

```bash
sudo systemctl status postgresql
sudo systemctl start postgresql
```

### Ошибка подключения

Проверьте:
1. PostgreSQL запущен: `sudo systemctl status postgresql`
2. Пользователь создан: `sudo -u postgres psql -c "\du"`
3. База данных создана: `sudo -u postgres psql -c "\l" | grep kunipy`
4. Права доступа: проверьте `/etc/postgresql/*/main/pg_hba.conf`

### Конфликты схемы

Пересоздайте схему:
```bash
PGPASSWORD=kunipy psql -h localhost -U kunipy -d kunipy << EOF
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO kunipy;
\q
EOF

# Затем запустите приложение - схема создастся автоматически
python run.py
```

### Миграция не работает

Проверьте:
1. SQLite файл существует
2. PostgreSQL база пустая (или используйте `ON CONFLICT DO NOTHING`)
3. Права доступа к обеим базам данных

## Безопасность

### Производственные настройки

1. **Измените пароль по умолчанию**:
```bash
sudo -u postgres psql -c "ALTER USER kunipy WITH PASSWORD 'strong_password_here';"
```

2. **Используйте переменные окружения**:
```env
MEMORY_POSTGRES_URL=postgresql://kunipy:${POSTGRES_PASSWORD}@localhost:5432/kunipy
```

3. **Ограничьте доступ**:
```bash
# Редактируйте pg_hba.conf для ограничения доступа
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

4. **Используйте SSL** (для production):
```env
MEMORY_POSTGRES_URL=postgresql://kunipy:password@localhost:5432/kunipy?sslmode=require
```

## Откат на SQLite

Если нужно вернуться к SQLite:

```env
# В .env
MEMORY_BACKEND=sqlite
MEMORY_DB_PATH=data/memory.db
```

Перезапустите приложение - оно автоматически переключится на SQLite.

## Ссылки

- [PostgreSQL документация](https://www.postgresql.org/docs/)
- [psycopg3 документация](https://www.psycopg.org/psycopg3/docs/)
- [ТЗ-002: Система памяти](./docs/TZ-002-memory.md)
