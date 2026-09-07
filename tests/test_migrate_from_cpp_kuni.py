"""Tests for tools/migrate_from_cpp_kuni.py against realistic C++ kuni fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from migrate_from_cpp_kuni import convert_config, convert_diary_entry, migrate_diary, migrate_prompts, migrate_working_memory  # noqa: E402


def test_convert_config_renames_endpoint_keys_anywhere_in_tree():
    cpp_config = {
        "general": {
            "character_name": "Kuni",
            "llm": {
                "model": "deepseek-v4-flash",
                "endpoint": {"baseUrl": "https://api.deepseek.com/v1/", "bearerKey": "secret"},
            },
        },
        "capabilities": {
            "take_photo": {
                "sd": {"endpoint": {"baseUrl": "http://localhost:7860/", "bearerKey": ""}},
            },
        },
        "misc": {"diary_token_count_trigger": 40000},
    }
    import tempfile
    import tomli_w

    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        tomli_w.dump(cpp_config, f)
        path = Path(f.name)

    converted = convert_config(path)
    assert converted["general"]["llm"]["endpoint"]["base_url"] == "https://api.deepseek.com/v1/"
    assert converted["general"]["llm"]["endpoint"]["bearer_key"] == "secret"
    assert converted["capabilities"]["take_photo"]["sd"]["endpoint"]["base_url"] == "http://localhost:7860/"
    # Untouched values must survive unchanged.
    assert converted["general"]["character_name"] == "Kuni"
    assert converted["misc"]["diary_token_count_trigger"] == 40000


def test_convert_diary_entry_renames_metadata_keys():
    raw = (
        "---\n"
        '{"score": 0.0, "confidence": 0.5, "lastUsed": "2026-01-01", "usageCount": 3, "embedding": [0.1, 0.2]}\n'
        "---\n"
        "Some memory text.\n"
    )
    converted = convert_diary_entry(raw, strip_embeddings=False)
    assert '"last_used": "2026-01-01"' in converted
    assert '"usage_count": 3' in converted
    assert "lastUsed" not in converted
    assert "usageCount" not in converted
    assert "Some memory text." in converted
    assert '"embedding"' in converted


def test_convert_diary_entry_strips_embeddings_when_requested():
    raw = '---\n{"score": 0.0, "confidence": 0.0, "embedding": [0.1, 0.2]}\n---\nBody text.\n'
    converted = convert_diary_entry(raw, strip_embeddings=True)
    assert "embedding" not in converted
    assert "Body text." in converted


def test_convert_diary_entry_without_metadata_passes_through():
    raw = "Just a plain entry with no metadata block."
    converted = convert_diary_entry(raw, strip_embeddings=False)
    assert converted == raw


def test_migrate_diary_writes_all_files(tmp_path):
    source = tmp_path / "src_diary"
    source.mkdir()
    (source / "1.md").write_text('---\n{"score": 0, "confidence": 0, "usageCount": 1}\n---\nEntry one.', encoding="utf-8")
    (source / "2.md").write_text("Plain entry two.", encoding="utf-8")

    dest = tmp_path / "dst_diary"
    count = migrate_diary(source, dest, strip_embeddings=False, dry_run=False)

    assert count == 2
    assert (dest / "1.md").exists()
    assert (dest / "2.md").exists()
    assert '"usage_count": 1' in (dest / "1.md").read_text(encoding="utf-8")


def test_migrate_diary_dry_run_writes_nothing(tmp_path):
    source = tmp_path / "src_diary"
    source.mkdir()
    (source / "1.md").write_text("Entry.", encoding="utf-8")
    dest = tmp_path / "dst_diary"

    count = migrate_diary(source, dest, strip_embeddings=False, dry_run=True)

    assert count == 1
    assert not dest.exists()


def test_migrate_working_memory_maps_to_things_to_remember_key(tmp_path):
    source_md = tmp_path / "working_memory.md"
    source_md.write_text("- remember to call papik back", encoding="utf-8")
    dest_json = tmp_path / "working_memory.json"

    ok = migrate_working_memory(source_md, dest_json, dry_run=False)

    assert ok is True
    data = json.loads(dest_json.read_text(encoding="utf-8"))
    assert data["things_to_remember"]["value"] == "- remember to call papik back"


def test_migrate_working_memory_missing_source_is_noop(tmp_path):
    ok = migrate_working_memory(tmp_path / "does_not_exist.md", tmp_path / "out.json", dry_run=False)
    assert ok is False


def test_migrate_working_memory_missing_source_prints_reason(tmp_path, capsys):
    migrate_working_memory(tmp_path / "does_not_exist.md", tmp_path / "out.json", dry_run=False)
    out = capsys.readouterr().out
    assert "not found" in out


def test_migrate_working_memory_empty_file_prints_reason(tmp_path, capsys):
    source_md = tmp_path / "working_memory.md"
    source_md.write_text("   \n  ", encoding="utf-8")
    ok = migrate_working_memory(source_md, tmp_path / "out.json", dry_run=False)
    assert ok is False
    assert "empty" in capsys.readouterr().out


def test_migrate_diary_missing_source_dir_prints_reason(tmp_path, capsys):
    count = migrate_diary(tmp_path / "does_not_exist", tmp_path / "dest", strip_embeddings=False, dry_run=False)
    assert count == 0
    assert "not found" in capsys.readouterr().out


def test_migrate_diary_empty_source_dir_prints_reason(tmp_path, capsys):
    source = tmp_path / "empty_diary"
    source.mkdir()
    count = migrate_diary(source, tmp_path / "dest", strip_embeddings=False, dry_run=False)
    assert count == 0
    assert "no .md entries" in capsys.readouterr().out


def test_migrate_prompts_extracts_character_files_and_mirrors_rest(tmp_path):
    source_prompts = tmp_path / "prompts"
    source_prompts.mkdir()
    (source_prompts / "character_base.md").write_text("---\nc\n---\nYou are Kuni.", encoding="utf-8")
    (source_prompts / "character_appearance.md").write_text("---\nc\n---\nBlue hair.", encoding="utf-8")
    (source_prompts / "system.md").write_text("Kernel prompt.", encoding="utf-8")
    (source_prompts / "anti_repeat.md").write_text("Anti-repeat nudge.", encoding="utf-8")

    dest = tmp_path / "kunipy_dest"
    dest.mkdir()
    migrate_prompts(source_prompts, dest, dry_run=False)

    assert (dest / "character_base.md").read_text(encoding="utf-8") == "---\nc\n---\nYou are Kuni."
    assert (dest / "character_appearance.md").read_text(encoding="utf-8") == "---\nc\n---\nBlue hair."
    # Files kunipy doesn't read yet are mirrored under dest/prompts/ for reference.
    assert (dest / "prompts" / "system.md").read_text(encoding="utf-8") == "Kernel prompt."
    assert (dest / "prompts" / "anti_repeat.md").read_text(encoding="utf-8") == "Anti-repeat nudge."


def test_migrate_prompts_does_not_overwrite_existing_character_files(tmp_path):
    source_prompts = tmp_path / "prompts"
    source_prompts.mkdir()
    (source_prompts / "character_base.md").write_text("new content", encoding="utf-8")

    dest = tmp_path / "kunipy_dest"
    dest.mkdir()
    (dest / "character_base.md").write_text("existing custom persona", encoding="utf-8")

    migrate_prompts(source_prompts, dest, dry_run=False)

    assert (dest / "character_base.md").read_text(encoding="utf-8") == "existing custom persona"


def test_migrate_prompts_dry_run_writes_nothing(tmp_path):
    source_prompts = tmp_path / "prompts"
    source_prompts.mkdir()
    (source_prompts / "character_base.md").write_text("content", encoding="utf-8")
    (source_prompts / "system.md").write_text("content", encoding="utf-8")

    dest = tmp_path / "kunipy_dest"
    dest.mkdir()
    migrate_prompts(source_prompts, dest, dry_run=True)

    assert not (dest / "character_base.md").exists()
    assert not (dest / "prompts").exists()


def test_migrate_prompts_missing_source_dir_is_noop(tmp_path):
    dest = tmp_path / "kunipy_dest"
    dest.mkdir()
    migrate_prompts(tmp_path / "does_not_exist", dest, dry_run=False)
    assert not (dest / "character_base.md").exists()
