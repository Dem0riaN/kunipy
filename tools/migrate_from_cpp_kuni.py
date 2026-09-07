#!/usr/bin/env python3
"""Migrate a working instance of the original C++ kuni (Alex2772/kuni) to kunipy.

IMPORTANT: `--source` must point at the *working directory* the C++ binary
actually runs from -- typically `build/bin/` inside the kuni repo checkout,
NOT the repo root itself. That's where `config.toml`, `diary/`,
`working_memory.md`, `prompts/`, and `tdlib/` actually live at runtime
(confirmed against the real C++ source, see comments below -- the repo root
only has the build system and source code).

The C++ and Python versions are close cousins -- most of the on-disk state is
either byte-compatible or a trivial rename/relocation away from it. This tool
copies and converts, in one pass:

1. **config.toml** (source: `<source>/config.toml`) -- almost every key
   already matches 1:1 (`general.character_name`,
   `misc.diary_token_count_trigger`, ...). The one real difference: the C++
   `Endpoint` struct serializes as `{baseUrl, bearerKey}`, while kunipy uses
   `{base_url, bearer_key}`. This tool walks the whole TOML tree and renames
   those keys wherever they appear (`general.llm.endpoint`,
   `general.embedding.endpoint`, `capabilities.take_photo.sd.endpoint`, ...),
   keeping every other value untouched.

2. **prompts/character_base.md, prompts/character_appearance.md**
   (source: `<source>/prompts/*.md`) -- byte-identical format (front-matter
   delimited by `---`, stripped by both versions before use), copied to
   kunipy's `character_base.md` / `character_appearance.md` at the kunipy
   working directory root (kunipy doesn't nest them under `prompts/`).

   The C++ version actually has *eleven more* prompt files under `prompts/`
   (`system.md`, `diary_save.md`, `sleep_consolidator.md`, `anti_repeat.md`,
   `photo_to_text.md`, `sticker_to_text.md`, `image_engineer_*.md`,
   `messages_epilogue.md`, `record_audio_speech.md`, ...) that fine-tune
   individual sub-behaviors kunipy currently implements directly in Python
   rather than as separate editable prompt files. This tool copies the
   *entire* `prompts/` directory into kunipy's `prompts/` folder for
   reference/safekeeping, but -- to be explicit -- **kunipy does not read
   anything from `prompts/` yet** other than what this script also copies
   out to `character_base.md`/`character_appearance.md`. Any customization
   you made to those other 11 files will not take effect until kunipy grows
   equivalent hooks.

3. **diary/*.md** (source: `<source>/diary/`, NOT `<source>/data/diary/`)
   -- same on-disk shape (`---\\n{json metadata}\\n---\\n{body}`), but the
   C++ version's JSON metadata uses camelCase keys (`lastUsed`,
   `usageCount`) where kunipy uses snake_case (`last_used`, `usage_count`).
   `score`, `confidence`, and `embedding` are already identical. This tool
   renames the keys and rewrites each entry in kunipy's format
   (`<dest>/data/diary/`).

   IMPORTANT: `embedding` vectors are only valid for the embedding *model*
   that produced them. If your kunipy `[general.embedding]` uses a
   different model than your C++ instance did, pass `--strip-embeddings` so
   kunipy recomputes them lazily (at the cost of one embedding call per
   entry, the first time each is queried) instead of silently comparing
   incompatible vectors.

4. **working_memory.md** (source: `<source>/working_memory.md`, NOT
   `<source>/data/working_memory.md`) -- the C++ version stores this as a
   single freeform markdown blob (LLM-authored, no structure kunipy could
   reuse directly). kunipy's own working-memory store is a small key/value
   cache; this tool imports the blob whole under the `things_to_remember`
   key, which is exactly the key kunipy's worker reads to build
   `<things_to_remember>` -- so nothing else needs to change.

5. **TDLib session** (`<source>/tdlib/`) -- both versions link the *same*
   TDLib library and use the same on-disk database format, so the session
   can be reused directly: this tool just copies the directory to where
   kunipy's `TelegramClient` expects it (`<dest>/data/tdlib/` by default).
   This means **no re-login is required**. Only do this after stopping the
   C++ instance -- TDLib's local database is not safe for two processes to
   hold open at once.

Deliberately NOT migrated (ephemeral/regenerable, safe to leave behind):
`cache/` (generated image/video cache), `logs/` and `logs_proxy/` (debug
request logs), `last_query.json` / `data/proxy/last_query.json` (last-request
debug dumps), `kuni_worker*.log`.

Usage
-----
    python tools/migrate_from_cpp_kuni.py --source /path/to/kuni/build/bin [options]

For the directory layout in the original request, that's e.g.:

    python tools/migrate_from_cpp_kuni.py \\
        --source /mnt/g/AI/kuni/build/bin \\
        --dest . \\
        --dry-run

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

try:
    import tomli
    import tomli_w
except ImportError:
    print(
        "error: this script needs the 'tomli' and 'tomli-w' packages to read/write config.toml.\n"
        "Install them with:\n"
        "    pip install tomli tomli-w\n"
        "or install kunipy's own dependencies from the repo root:\n"
        "    pip install -e .",
        file=sys.stderr,
    )
    raise SystemExit(1)

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


# --- 2. character files / prompts directory ---------------------------------

_CHARACTER_FILES = {
    "character_base.md": "character_base.md",
    "character_appearance.md": "character_appearance.md",
}

# Present in C++ kuni's prompts/ but not (yet) read by kunipy at all. Copied
# for reference/safekeeping only -- listed explicitly so we can warn loudly.
_UNUSED_BY_KUNIPY = [
    "system.md", "photo_to_text.md", "sticker_to_text.md", "anti_repeat.md",
    "diary_save.md", "sleep_consolidator.md", "record_audio_speech.md",
    "messages_epilogue.md", "image_engineer_system.md",
    "image_engineer_instructions.md", "image_assess_system.md",
]


def migrate_prompts(source_prompts_dir: Path, dest_root: Path, dry_run: bool) -> None:
    """Copy prompts/character_base.md and prompts/character_appearance.md to
    kunipy's working-dir root, and mirror the rest of prompts/ verbatim into
    kunipy's own prompts/ folder for reference (unused by kunipy today)."""
    if not source_prompts_dir.is_dir():
        print(f"  prompts: {source_prompts_dir} not found, skipping")
        return

    for src_name, dest_name in _CHARACTER_FILES.items():
        src = source_prompts_dir / src_name
        if not src.is_file():
            print(f"  character: {src} not found, skipping")
            continue
        dst = dest_root / dest_name
        print(f"  character: {src} -> {dst}" + (" (dry-run)" if dry_run else ""))
        if dry_run:
            continue
        if dst.exists():
            print(f"  ! {dst} already exists, leaving it alone (kunipy never overwrites these either)")
        else:
            shutil.copyfile(src, dst)

    found_unused = [n for n in _UNUSED_BY_KUNIPY if (source_prompts_dir / n).is_file()]
    if found_unused:
        dest_prompts_dir = dest_root / "prompts"
        print(f"  prompts: copying {len(found_unused)} additional prompt file(s) to {dest_prompts_dir} "
              f"for reference (kunipy does not read these yet: {', '.join(found_unused)})"
              + (" (dry-run)" if dry_run else ""))
        if not dry_run:
            dest_prompts_dir.mkdir(parents=True, exist_ok=True)
            for name in found_unused:
                shutil.copyfile(source_prompts_dir / name, dest_prompts_dir / name)


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

    if (source / "CMakeLists.txt").exists() and not (source / "config.toml").exists():
        print(
            f"error: {source} looks like the kuni repo checkout (has CMakeLists.txt), not its runtime "
            f"working directory. Point --source at the folder containing config.toml, diary/, "
            f"working_memory.md, prompts/, and tdlib/ -- typically <repo>/build/bin.",
            file=sys.stderr,
        )
        return 1

    print(f"Migrating {source} -> {dest}" + (" [DRY RUN]" if args.dry_run else ""))
    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)

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

    # 2. character files (+ rest of prompts/, for reference)
    if not args.skip_character:
        migrate_prompts(source / "prompts", dest, args.dry_run)

    # 3. diary (real path: <source>/diary/, NOT <source>/data/diary/)
    if not args.skip_diary:
        n = migrate_diary(source / "diary", dest / "data" / "diary", args.strip_embeddings, args.dry_run)
        print(f"  diary: {n} entries" + (" would be " if args.dry_run else " ") + "converted")

    # 4. working memory (real path: <source>/working_memory.md, NOT <source>/data/working_memory.md)
    if not args.skip_working_memory:
        migrate_working_memory(source / "working_memory.md", dest / "data" / "working_memory.json", args.dry_run)

    # 5. tdlib session
    if not args.skip_tdlib:
        migrate_tdlib_session(source / "tdlib", dest / "data" / "tdlib", args.dry_run)

    print("Done." if not args.dry_run else "Dry run complete, nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
