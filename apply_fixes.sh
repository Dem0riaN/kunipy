#!/bin/bash
# Patch for fixing TelegramClient and adding embedding config
# Apply on Linux machine: bash apply_fixes.sh

echo "Applying fixes to kunipy-main..."

# Fix 1: Add embedding field to Config
echo "1. Adding embedding field to Config..."
sed -i '/# Core LLM/,/llm: EndpointAndModel/a\
\
    # Embedding model (for memory system and diary)\
    embedding: EndpointAndModel = field(default_factory=EndpointAndModel)' src/config.py

# Fix 2: Add papik_name and character_nickname
echo "2. Adding papik_name and character_nickname to Config..."
sed -i 's/character_name: str = "Куни"/character_name: str = "Куни"\
    character_nickname: str = ""\
\
    # Owner (papik)\
    papik_name: str = ""\
    papik_chat_id: int = 0/' src/config.py

# Fix 3: Remove duplicate papik_chat_id
echo "3. Removing duplicate papik_chat_id..."
sed -i '/# Lockdown/,/lockdown: LockdownMode/{ /papik_chat_id: int = 0/d; }' src/config.py

# Fix 4: Fix TelegramClient initialization in DI container
echo "4. Fixing TelegramClient initialization..."
sed -i 's/phone=config.telegram_phone,//' src/di/container.py
sed -i 's/database_directory=config.telegram_database_directory/database_dir=config.telegram_database_directory/' src/di/container.py

# Fix 5: Add embedding provider with fallback
echo "5. Adding embedding provider logic..."
cat > /tmp/embedding_fix.txt << 'EOF'
    # Embedding provider (separate endpoint for embeddings)
    # If embedding config is empty, fallback to main LLM
    embedding_endpoint = config.embedding if config.embedding.model else config.llm
    embedding_provider = OpenAIChat(
        endpoint=embedding_endpoint,
        timeout=30,
        max_retries=2,
    )
EOF

sed -i '/# Embedding provider (reuses OpenAI chat for now)/,/embedding_provider = openai_chat  # OpenAIChat implements IEmbeddingProvider/{
    r /tmp/embedding_fix.txt
    d
}' src/di/container.py

echo "✅ All fixes applied successfully!"
echo ""
echo "Test the fixes:"
echo "  python -c 'from src.config import Config; c = Config(); print(f\"embedding: {c.embedding.model}\")'"
echo "  python run.py"
