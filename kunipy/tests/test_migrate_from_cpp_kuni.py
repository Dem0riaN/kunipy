"""Tests for tools/migrate_from_cpp_kuni.py against realistic C++ kuni fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from migrate_from_cpp_kuni import convert_config, convert_diary_entry, migrate_diary, migrate_working_memory  # noqa: E402


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
