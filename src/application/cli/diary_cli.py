"""Diary CLI - operator browser for the diary (Phase 6).

Usage:
    python -m src.application.cli.diary_cli list [--limit N] [--sort date|confidence|importance|score]
    python -m src.application.cli.diary_cli show <entry_id>
    python -m src.application.cli.diary_cli search "<query>" [--top N] [--semantic|--text|--tags]
    python -m src.application.cli.diary_cli stats
    python -m src.application.cli.diary_cli tags

Kuni itself has no access to this tool - operator utility only.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Bootstrap project root for src.* imports
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_diary():
    """Build a read-only Diary instance from config."""
    from src.config import load_config
    from src.diary import Diary

    config = load_config()
    diary = Diary(
        diary_dir=Path(config.diary_dir),
        openai_chat=None,  # Embeddings only needed for --semantic; created lazily below
        config=config,
    )
    return diary, config


async def cmd_list(args: argparse.Namespace) -> int:
    from src.diary import Diary  # noqa: F401

    diary, config = _load_diary()
    entries = await diary.get_all_entries()

    key = args.sort
    if key == "date":
        entries.sort(key=lambda e: int(e.metadata.get("created_at", 0)), reverse=True)
    elif key in ("confidence", "importance", "score"):
        entries.sort(key=lambda e: float(e.metadata.get(key, 0.0)), reverse=True)

    limit = args.limit
    if limit:
        entries = entries[:limit]

    print(f"{'ID':<12} {'Date':<16} {'Kind':<12} {'Conf':>6} {'Imp':>5} {'Score':>6}  Preview")
    print("-" * 100)
    for e in entries:
        ts = int(e.metadata.get("created_at", 0))
        date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M") if ts else "unknown"
        kind = str(e.metadata.get("kind", "other"))[:12]
        conf = float(e.metadata.get("confidence", 0.0))
        imp = float(e.metadata.get("importance", 0.5))
        score = float(e.metadata.get("score", 0.0))
        preview = " ".join(e.body.split())[:80]
        print(f"{e.id:<12} {date:<16} {kind:<12} {conf:>6.2f} {imp:>5.2f} {score:>6.2f}  {preview}")

    print(f"\nTotal: {len(entries)} entries")
    return 0


async def cmd_show(args: argparse.Namespace) -> int:
    import json

    diary, _ = _load_diary()
    entry = await diary.get_entry(args.entry_id)
    if entry is None:
        print(f"Entry not found: {args.entry_id}")
        return 1

    meta = dict(entry.metadata)
    meta.pop("embedding", None)  # too large to print
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("\n--- body ---\n")
    print(entry.body)
    return 0


async def cmd_search(args: argparse.Namespace) -> int:
    import numpy as np

    diary, config = _load_diary()
    query = args.query
    top = args.top

    if args.tags or query.startswith("#") or args.text:
        results = await diary.search_by_text(query, max_entries=top)
    else:
        # semantic
        if config.embedding.model:
            from src.openai_chat import OpenAIChat

            openai = OpenAIChat(endpoint=config.embedding)
            try:
                emb = await openai.embedding(query, model=config.embedding.model)
                results = await diary.query(np.asarray(emb, dtype=np.float64), max_entries=top)
            finally:
                await openai.close()
        else:
            print("Embedding model not configured; use --text or --tags")
            return 1

    if not results:
        print("No results.")
        return 0

    for entry, score in results:
        ts = int(entry.metadata.get("created_at", 0))
        date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M") if ts else "unknown"
        conf = float(entry.metadata.get("confidence", 0.0))
        preview = " ".join(entry.body.split())[:120]
        print(f"[{score:.3f}] {entry.id}  {date}  conf={conf:+.2f}  {preview}")
    return 0


async def cmd_stats(args: argparse.Namespace) -> int:
    diary, config = _load_diary()
    entries = await diary.get_all_entries()
    total = len(entries)
    print(f"Diary: {config.diary_dir}")
    print(f"Total entries: {total}")
    if total == 0:
        return 0

    confs = [float(e.metadata.get("confidence", 0.0)) for e in entries]
    print(f"Average confidence: {sum(confs) / total:+.3f}")
    print(f"Immutable anchors (conf=1): {sum(1 for c in confs if c >= 1.0)}")

    kinds: dict[str, int] = {}
    for e in entries:
        k = str(e.metadata.get("kind", "other"))
        kinds[k] = kinds.get(k, 0) + 1
    print("Kind distribution:")
    for k, v in sorted(kinds.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {k:<20} {v}")

    ts_vals = [int(e.metadata.get("created_at", 0)) for e in entries if e.metadata.get("created_at")]
    if ts_vals:
        newest = max(ts_vals)
        oldest = min(ts_vals)
        print(f"Newest:  {datetime.fromtimestamp(newest, tz=UTC).strftime('%Y-%m-%d %H:%M')}")
        print(f"Oldest:  {datetime.fromtimestamp(oldest, tz=UTC).strftime('%Y-%m-%d %H:%M')}")
    return 0


async def cmd_tags(args: argparse.Namespace) -> int:
    diary, _ = _load_diary()
    entries = await diary.get_all_entries()

    tags: dict[str, int] = {}
    for e in entries:
        raw = str(e.metadata.get("tags", ""))
        for t in raw.split(","):
            t = t.strip().lstrip("#").lower()
            if t:
                tags[t] = tags.get(t, 0) + 1

    if not tags:
        print("No tags found.")
        return 0

    for t, c in sorted(tags.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{c:>5}  {t}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diary_cli", description="Diary operator browser")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List diary entries")
    p_list.add_argument("--limit", type=int, default=0, help="Max entries (0 = all)")
    p_list.add_argument("--sort", choices=["date", "confidence", "importance", "score"], default="date")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show one entry in full")
    p_show.add_argument("entry_id")
    p_show.set_defaults(func=cmd_show)

    p_search = sub.add_parser("search", help="Search entries")
    p_search.add_argument("query")
    p_search.add_argument("--top", type=int, default=10)
    group = p_search.add_mutually_exclusive_group()
    group.add_argument("--semantic", action="store_true", help="Vector search (default)")
    group.add_argument("--text", action="store_true", help="Substring search")
    group.add_argument("--tags", action="store_true", help="Tag search")
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="Diary statistics")
    p_stats.set_defaults(func=cmd_stats)

    p_tags = sub.add_parser("tags", help="List tags with counts")
    p_tags.set_defaults(func=cmd_tags)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(args.func(args))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
