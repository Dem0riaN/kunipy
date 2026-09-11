"""Debug script to test placeholder conversion - detailed."""

import asyncio
import psycopg

async def test():
    conn = await psycopg.AsyncConnection.connect(
        "postgresql://kunipy:kunipy@localhost:5432/kunipy",
        autocommit=True
    )

    query1 = "SELECT * FROM users WHERE user_id = ?"
    params = ("telegram:99999",)

    # Manual conversion
    query2 = query1.replace('?', '$1', 1)

    print(f"Query 1 (original): {repr(query1)}")
    print(f"Query 2 (converted): {repr(query2)}")
    print(f"Params: {params}")
    print()

    # Test byte representation
    print(f"Query 2 bytes: {query2.encode('utf-8')}")
    print()

    # Try direct query with $1
    query3 = "SELECT * FROM users WHERE user_id = $1"
    print(f"Query 3 (hardcoded): {repr(query3)}")

    async with conn.cursor() as cur:
        try:
            print("Trying hardcoded $1 query...")
            await cur.execute(query3, params)
            print("✓ Hardcoded query works")
        except Exception as e:
            print(f"✗ Hardcoded query failed: {e}")

        try:
            print("\nTrying converted query...")
            await cur.execute(query2, params)
            print("✓ Converted query works")
        except Exception as e:
            print(f"✗ Converted query failed: {e}")

    # Check if they're equal
    print(f"\nAre queries equal? {query2 == query3}")
    print(f"Query 2 repr: {repr(query2)}")
    print(f"Query 3 repr: {repr(query3)}")

    await conn.close()

asyncio.run(test())
