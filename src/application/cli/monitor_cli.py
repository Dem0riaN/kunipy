"""Monitor CLI - operator status utility (Phase 6).

Usage:
    python -m src.application.cli.monitor_cli status
    python -m src.application.cli.monitor_cli memory
    python -m src.application.cli.monitor_cli prompts show [system|character_base|...]
    python -m src.application.cli.monitor_cli prompts diff <prompt_name>

Kuni itself has no access to this tool - operator utility only.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROMPTS_DIR = ROOT / "prompts"


def _config():
    from src.config import load_config

    return load_config()


async def cmd_status(args: argparse.Namespace) -> int:
    config = _config()
    print(f"Character: {config.character_name}")
    print(f"Diary enabled: {config.diary_enabled}")

    if config.diary_enabled:
        from src.diary import Diary

        diary = Diary(diary_dir=Path(config.diary_dir), openai_chat=None, config=config)
        entries = await diary.get_all_entries()
        print(f"Diary entries: {len(entries)}")
        if entries:
            ts_vals = [int(e.metadata.get("created_at", 0)) for e in entries if e.metadata.get("created_at")]
            if ts_vals:
                print(f"Last entry: {datetime.fromtimestamp(max(ts_vals), tz=UTC).strftime('%Y-%m-%d %H:%M')}")
            cons = [
                int(e.metadata.get("consolidated_at", 0))
                for e in entries
                if e.metadata.get("consolidated_at")
            ]
            if cons:
                print(f"Last consolidation: {datetime.fromtimestamp(max(cons), tz=UTC).strftime('%Y-%m-%d %H:%M')}")
            else:
                print("Last consolidation: never")

        chroma = ROOT / config.diary_chroma_dir
        if chroma.exists():
            size_mb = sum(f.stat().st_size for f in chroma.rglob("*") if f.is_file()) / 1e6
            print(f"ChromaDB size: {size_mb:.2f} MB ({chroma})")
        else:
            print(f"ChromaDB: not created yet ({chroma})")

    print(f"Auto-RAG enabled: {config.diary_auto_rag_enabled}")
    print(f"Sleep consolidation: daily 04:00 (sleep_chance={config.sleep_chance})")
    return 0


async def cmd_memory(args: argparse.Namespace) -> int:
    config = _config()
    wm_path = ROOT / "working_memory.md"
    if not wm_path.exists():
        print(f"Working memory file not found: {wm_path}")
        return 0

    print(f"=== {wm_path} ===\n")
    print(wm_path.read_text(encoding="utf-8"))

    if config.memory_enabled:
        print(f"\n(Additional SQL-backed memory active: backend={config.memory_backend})")
    return 0


async def cmd_prompts_show(args: argparse.Namespace) -> int:
    from src.prompt_loader import _substitute_prompt_vars

    config = _config()
    name = args.prompt_name
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        candidates = sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
        print(f"Prompt not found: {name}")
        print(f"Available: {', '.join(candidates)}")
        return 1

    raw = path.read_text(encoding="utf-8")
    rendered = _substitute_prompt_vars(raw, config)
    print(rendered)
    return 0


async def cmd_prompts_diff(args: argparse.Namespace) -> int:
    """Diff a prompt against the packaged default template (git-less fallback).

    The 'default' is the same file when unmodified, so this reports the diff
    between the on-disk prompt and a rebuilt version: for now we compare the
    raw file and the variable-substituted rendering, which shows what the
    model actually receives versus what is authored.
    """
    from src.prompt_loader import _substitute_prompt_vars

    config = _config()
    name = args.prompt_name
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        print(f"Prompt not found: {name}")
        return 1

    raw = path.read_text(encoding="utf-8").splitlines()
    rendered = _substitute_prompt_vars("\n".join(raw), config).splitlines()

    diff = list(difflib.unified_diff(raw, rendered, fromfile=f"{name}.md (authored)", tofile=f"{name}.md (rendered)", lineterm=""))
    if not diff:
        print(f"{name}.md: no variable substitutions applied (identical).")
        return 0
    print("\n".join(diff))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="monitor_cli", description="Kunipy operator monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Application and memory status")
    p_status.set_defaults(func=cmd_status)

    p_mem = sub.add_parser("memory", help="Current working memory")
    p_mem.set_defaults(func=cmd_memory)

    p_prompts = sub.add_parser("prompts", help="Inspect prompts")
    prompts_sub = p_prompts.add_subparsers(dest="subcommand", required=True)
    p_show = prompts_sub.add_parser("show", help="Show prompt with variable substitution")
    p_show.add_argument("prompt_name", nargs="?", default="system")
    p_show.set_defaults(func=cmd_prompts_show)
    p_diff = prompts_sub.add_parser("diff", help="Diff authored vs rendered prompt")
    p_diff.add_argument("prompt_name")
    p_diff.set_defaults(func=cmd_prompts_diff)

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
