#!/usr/bin/env python3
"""Diagnose why the diary "ask" tool returns "No relevant memories found."

Runs a query against every diary entry with the relevance threshold
disabled, so you can see:

1. How many entries actually got loaded from `data/diary/` (a low/zero
   count means a path or file-parsing problem).
2. The real similarity score of each entry against your query, *before*
   `diary_min_relatedness` filters anything out. If entries exist with
   near-zero/random-looking scores across the board (no clear front-runner
   that at least loosely relates to the query), that's the signature of
   embeddings computed by a *different* embedding model than the one your
   kunipy is currently configured to use -- in which case, re-run the
   migration with `--strip-embeddings` and let kunipy recompute them, or
   just wait for the sleep-consolidation loop / natural re-querying to fix
   it up over time (embeddings are recomputed on first `save()` after being
   read as `None`, but `--strip-embeddings` forces this immediately for all
   entries).

Usage:
    python tools/diagnose_diary.py "your test query"
    python tools/diagnose_diary.py "your test query" --diary-dir data/diary
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config  # noqa: E402
from src.diary import Diary  # noqa: E402
from src.openai_chat import OpenAIChat  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="Text to search the diary for")
    parser.add_argument("--diary-dir", default="data/diary", help="Diary directory (default: data/diary)")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    args = parser.parse_args()

    diary_dir = Path(args.diary_dir)
    if not diary_dir.is_dir():
        print(f"error: {diary_dir} does not exist or is not a directory", file=sys.stderr)
        return 1

    md_files = sorted(diary_dir.glob("*.md"))
    print(f"Found {len(md_files)} .md file(s) in {diary_dir}")
    if not md_files:
        print("-> Nothing to search. Check that the migration actually wrote files here.")
        return 1

    config = load_config(args.config)
    print(f"Using embedding model: {config.embedding.model} @ {config.embedding.endpoint.base_url}")
    print(f"Configured diary_min_relatedness: {config.diary_min_relatedness}")
    print()

    openai = OpenAIChat(endpoint=config.embedding)
    diary = Diary(diary_dir=diary_dir, openai=openai, embedding_model=config.embedding.model)

    entries = await diary.get_all()
    print(f"Diary loaded {len(entries)} entr(ies) into memory.")
    with_embedding = sum(1 for e in entries if e.embedding is not None)
    print(f"  - {with_embedding} already have a stored embedding")
    print(f"  - {len(entries) - with_embedding} will need one computed on first query (this may take a while)")
    print()

    query_vector = await openai.embedding(args.query)

    # Query with the relevance threshold disabled (min_relatedness=0.0) so
    # every entry shows up, ranked by real score.
    results = await diary.query(query_vector, max_entries=len(entries), min_relatedness=0.0)

    print(f'Scores for query "{args.query}" (threshold disabled, showing all {len(results)}):')
    print(f"{'score':>7}  {'id':<16}  body preview")
    print("-" * 70)
    for entry, score in results:
        preview = entry.body.strip().replace("\n", " ")[:60]
        flag = " <-- above your configured threshold" if score >= config.diary_min_relatedness else ""
        print(f"{score:7.3f}  {entry.id:<16}  {preview}{flag}")

    print()
    top_score = results[0][1] if results else 0.0
    if top_score < 0.55:
        print(
            "Diagnosis: even the best-matching entry scores quite low across the board. "
            "This is the typical signature of diary embeddings that were computed by a "
            "DIFFERENT embedding model than the one currently configured -- cosine similarity "
            "between incompatible embedding spaces is close to random.\n"
            "Fix: re-run the migration with --strip-embeddings, e.g.:\n"
            "    python tools/migrate_from_cpp_kuni.py --source <cpp working dir> --dest . "
            "--strip-embeddings --skip-config --skip-character --skip-tdlib --skip-working-memory\n"
            "(kunipy will recompute each entry's embedding, lazily, the next time it's queried)."
        )
    elif top_score < config.diary_min_relatedness:
        print(
            f"Diagnosis: relevant-looking entries exist (top score {top_score:.3f}) but fall just "
            f"below your configured diary_min_relatedness ({config.diary_min_relatedness}). "
            "Consider lowering [misc] diary_min_relatedness slightly in config.toml."
        )
    else:
        print("Diagnosis: retrieval looks healthy for this query -- at least one entry clears your threshold.")

    await openai.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
