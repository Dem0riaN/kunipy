#!/usr/bin/env python3
"""Migrate a working instance of the original C++ kuni (Alex2772/kuni) to kunipy.

The C++ and Python versions are close cousins -- most of the on-disk state is
either byte-compatible or a trivial rename away from it. This tool copies and
converts, in one pass:

1. **config.toml** -- almost every key already matches 1:1
   (`general.character_name`, `misc.diary_token_count_trigger`, ...). The one
   real difference: the C++ `Endpoint` struct serializes as
   `{baseUrl, bearerKey}`, while kunipy uses `{base_url, bearer_key}`. This
   tool walks the whole TOML tree and renames those keys wherever they
   appear (`general.llm.endpoint`, `general.embedding.endpoint`,
   `capabilities.take_photo.sd.endpoint`, `capabilities.vision.*.endpoint`,
   `capabilities.hearing.llm_audio_to_text.endpoint`), keeping every other
   value untouched.

2. **character_base.md / character_appearance.md** -- byte-identical format
   (front-matter delimited by `---`, stripped by both versions before use),
   copied as-is.

3. **data/diary/*.md** -- same on-disk shape
   (`---\\n{json metadata}\\n---\\n{body}`), but the C++ version's JSON
   metadata uses camelCase keys (`lastUsed`, `usageCount`) where kunipy uses
   snake_case (`last_used`, `usage_count`). `score`, `confidence`, and
   `embedding` are already identical. This tool renames the keys and
   rewrites each entry in kunipy's format.

   IMPORTANT: `embedding` vectors are only valid for the embedding *model*
   that produced them. If your kunipy `[general.embedding]` uses a
   different model than your C++ instance did, pass `--strip-embeddings` so
   kunipy recomputes them lazily (at the cost of one embedding call per
   entry, the first time each is queried) instead of silently comparing
   incompatible vectors.

4. **data/working_memory.md** -- the C++ version stores this as a single
   freeform markdown blob (LLM-authored, no structure kunipy could reuse
   directly). kunipy's own working-memory store is a small key/value cache;
   this tool imports the blob whole under the `things_to_remember` key,
   which is exactly the key kunipy's worker reads to build
   `<things_to_remember>` -- so nothing else needs to change.

5. **TDLib session** (`tdlib/` in the C++ working directory) -- both
   versions link the *same* TDLib library and use the same on-disk database
   format, so the session can be reused directly: this tool just copies the
   directory to where kunipy's `TelegramClient` expects it
   (`data/tdlib/` by default). This means **no re-login is required**.
   Only do this after stopping the C++ instance -- TDLib's local database
   is not safe for two processes to hold open at once.

Usage
-----
    python tools/migrate_from_cpp_kuni.py --source /path/to/cpp/kuni/workdir [options]

Run with `--dry-run` first to see exactly what would be written, without
touching anything.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

import tomli
import tomli_w

# --- 1. config.toml ---------------------------------------------------------

# Any TOML table with exactly these two keys is a C++ `Endpoint` struct.
_CPP_ENDPOINT_KEYS = {"baseUrl", "bearerKey"}
_ENDPOINT_KEY_RENAME = {"baseUrl": "base_url", "bearerKey": "bearer_key"}


def _convert_toml_value(value: Any) -> Any:
    """Recursively rename Endpoint keys anywhere they appear in the tree."""
    if isinstance(value, dict):
        if _CPP_ENDPOINT_KEYS.issubset(value.keys()):
            return {_ENDPOINT_KEY_RENAME.get(k, k): _convert_toml_value(v) for k, v in value.items()}
        return {k: _convert_toml_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_toml_value(v) for v in value]
    return value


def convert_config(source_toml: Path) -> Dict[str, Any]:
    """Load a C++ kuni config.toml and return a kunipy-shaped dict."""
    with open(source_toml, "rb") as f:
        data = tomli.load(f)
    return _convert_toml_value(data)


# --- 3. diary entries --------------------------------------------------------

_DIARY_METADATA_RENAME = {
    "lastUsed": "last_used",
    "usageCount": "usage_count",
    # score, confidence, embedding: identical already.
}


def convert_diary_entry(raw_text: str, strip_embeddings: bool) -> str:
    """Convert one C++ diary .md file's content to kunipy's format."""
    text = raw_text.strip("\n")
    if not text.startswith("---"):
        # No metadata block -- already a valid freeform entry either way.
        return text

    end = text.find("---", 3)
    if end == -1:
        return text

    meta_raw = text[3:end].strip()
    body = text[end + 3:].strip("\n")

    try:
        metadata = json.loads(meta_raw)
    except json.JSONDecodeError:
        # Not JSON we recognize -- leave the file untouched rather than guess.
        return text

    converted = {}
    for key, value in metadata.items():
        converted[_DIARY_METADATA_RENAME.get(key, key)] = value

    if strip_embeddings:
        converted.pop("embedding", None)

    meta_json = json.dumps(converted, indent=2, ensure_ascii=False)
    return f"---\n{meta_json}\n---\n\n{body}"


def migrate_diary(source_dir: Path, dest_dir: Path, strip_embeddings: bool, dry_run: bool) -> int:
    if not source_dir.is_dir():
        return 0
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for entry_path in sorted(source_dir.glob("*.md")):
        converted = convert_diary_entry(entry_path.read_text(encoding="utf-8"), strip_embeddings)
        dest_path = dest_dir / entry_path.name
        print(f"  diary: {entry_path.name}" + (" (dry-run)" if dry_run else ""))
        if not dry_run:
            dest_path.write_text(converted, encoding="utf-8")
        count += 1
    return count


# --- 4. working memory --------------------------------------------------------

def migrate_working_memory(source_md: Path, dest_json: Path, dry_run: bool) -> bool:
    if not source_md.is_file():
        return False
    text = source_md.read_text(encoding="utf-8").strip()
    if not text:
        return False

    print(f"  working memory: {source_md} -> {dest_json} (key='things_to_remember')" + (" (dry-run)" if dry_run else ""))
    if dry_run:
        return True

    dest_json.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if dest_json.exists():
        try:
            existing = json.loads(dest_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    existing["things_to_remember"] = {"value": text, "timestamp": 0, "ttl": None}
    dest_json.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# --- 5. TDLib session ---------------------------------------------------------

def migrate_tdlib_session(source_dir: Path, dest_dir: Path, dry_run: bool) -> bool:
    if not source_dir.is_dir():
        return False
    print(f"  tdlib session: {source_dir} -> {dest_dir}" + (" (dry-run)" if dry_run else ""))
    if dry_run:
        return True
    if dest_dir.exists():
        print(f"  ! {dest_dir} already exists, refusing to overwrite -- remove it first if you want to replace it.")
        return False
    shutil.copytree(source_dir, dest_dir)
    return True


# --- main ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate an Alex2772/kuni (C++) working directory to kunipy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", required=True, type=Path, help="Path to the C++ kuni working directory (where config.toml, data/, tdlib/ live)")
    parser.add_argument("--dest", default=Path("."), type=Path, help="kunipy working directory (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing anything")
    parser.add_argument("--strip-embeddings", action="store_true", help="Drop diary embedding vectors instead of copying them (use this if you're switching embedding models)")
    parser.add_argument("--skip-config", action="store_true")
    parser.add_argument("--skip-character", action="store_true")
    parser.add_argument("--skip-diary", action="store_true")
    parser.add_argument("--skip-working-memory", action="store_true")
    parser.add_argument("--skip-tdlib", action="store_true")
    args = parser.parse_args()

    source: Path = args.source
    dest: Path = args.dest
    if not source.is_dir():
        print(f"error: --source {source} is not a directory", file=sys.stderr)
        return 1

    print(f"Migrating {source} -> {dest}" + (" [DRY RUN]" if args.dry_run else ""))

    # 1. config.toml
    if not args.skip_config:
        src_config = source / "config.toml"
        if src_config.is_file():
            converted = convert_config(src_config)
            dest_config = dest / "config.toml"
            print(f"  config: {src_config} -> {dest_config}" + (" (dry-run)" if args.dry_run else ""))
            if dest_config.exists():
                print(f"  ! {dest_config} already exists -- writing to config.toml.migrated instead. "
                      f"Diff and merge by hand, since your kunipy config.toml likely has comments/extra "
                      f"fields (proxy.port, proxy.upstream, metrics_*) that don't exist in the C++ version.")
                dest_config = dest / "config.toml.migrated"
            if not args.dry_run:
                with open(dest_config, "wb") as f:
                    tomli_w.dump(converted, f)
        else:
            print(f"  config: no config.toml found in {source}, skipping")

    # 2. character files
    if not args.skip_character:
        for name in ("character_base.md", "character_appearance.md"):
            src = source / name
            if src.is_file():
                dst = dest / name
                print(f"  character: {src} -> {dst}" + (" (dry-run)" if args.dry_run else ""))
                if not args.dry_run:
                    if dst.exists():
                        print(f"  ! {dst} already exists, leaving it alone (kunipy never overwrites these either)")
                    else:
                        shutil.copyfile(src, dst)
            else:
                print(f"  character: {src} not found, skipping")

    # 3. diary
    if not args.skip_diary:
        n = migrate_diary(source / "data" / "diary", dest / "data" / "diary", args.strip_embeddings, args.dry_run)
        print(f"  diary: {n} entries" + (" would be " if args.dry_run else " ") + "converted")

    # 4. working memory
    if not args.skip_working_memory:
        migrate_working_memory(source / "data" / "working_memory.md", dest / "data" / "working_memory.json", args.dry_run)

    # 5. tdlib session
    if not args.skip_tdlib:
        migrate_tdlib_session(source / "tdlib", dest / "data" / "tdlib", args.dry_run)

    print("Done." if not args.dry_run else "Dry run complete, nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
