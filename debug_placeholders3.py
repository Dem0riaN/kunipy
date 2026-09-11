"""Test different placeholder formats for psycopg3."""

import asyncio
import psycopg

async def test():
    conn = await psycopg.AsyncConnection.connect(
        "postgresql://kunipy:kunipy@localhost:5432/kunipy",
        autocommit=True
    )

    params = ("telegram:99999",)

    # psycopg3 uses %s style placeholders by default
    queries = [
        ("$1 style", "SELECT * FROM users WHERE user_id = $1"),
        ("%s style", "SELECT * FROM users WHERE user_id = %s"),
        ("%(name)s style", "SELECT * FROM users WHERE user_id = %(user_id)s"),
    ]

    for name, query in queries:
        async with conn.cursor() as cur:
            try:
                print(f"Trying {name}: {query}")
                if "%(user_id)s" in query:
                    await cur.execute(query, {"user_id": params[0]})
                else:
                    await cur.execute(query, params)
                print(f"✓ {name} works!\n")
            except Exception as e:
                print(f"✗ {name} failed: {e}\n")

    await conn.close()

asyncio.run(test())
