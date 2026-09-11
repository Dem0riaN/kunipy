"""Debug script to test placeholder conversion."""

query = "SELECT * FROM users WHERE user_id = ?"
params = ("telegram:99999",)

print(f"Original query: {query}")
print(f"Params: {params}")
print(f"Question marks in query: {query.count('?')}")
print(f"Params count: {len(params)}")
print()

# Convert
converted_query = query
if params and '?' in query:
    for i in range(len(params)):
        converted_query = converted_query.replace('?', f'${i+1}', 1)

print(f"Converted query: {converted_query}")
print(f"Expected: SELECT * FROM users WHERE user_id = $1")
print()

# Test actual PostgreSQL execution
import asyncio
import psycopg

async def test():
    conn = await psycopg.AsyncConnection.connect(
        "postgresql://kunipy:kunipy@localhost:5432/kunipy",
        autocommit=True
    )

    async with conn.cursor() as cur:
        # Try with converted query
        try:
            await cur.execute(converted_query, params)
            print("✓ Query executed successfully")
            rows = await cur.fetchall()
            print(f"✓ Fetched {len(rows)} rows")
        except Exception as e:
            print(f"✗ Error: {e}")

    await conn.close()

asyncio.run(test())
