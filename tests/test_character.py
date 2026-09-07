"""Tests for character.py: default file creation and system prompt building."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.character import build_system_prompt, ensure_character_files  # noqa: E402
from src.config import Config  # noqa: E402


def test_ensure_character_files_creates_defaults(tmp_path):
    cfg = Config()
    base_path, appearance_path = ensure_character_files(cfg, base_dir=str(tmp_path))
    assert base_path.exists()
    assert appearance_path.exists()
    assert cfg.character_name in base_path.read_text(encoding="utf-8")
    assert cfg.character_name in appearance_path.read_text(encoding="utf-8")


def test_ensure_character_files_does_not_overwrite_edits(tmp_path):
    cfg = Config()
    base_path, _ = ensure_character_files(cfg, base_dir=str(tmp_path))
    base_path.write_text("My custom persona text.", encoding="utf-8")

    # Calling again must not touch the file the user edited.
    ensure_character_files(cfg, base_dir=str(tmp_path))
    assert base_path.read_text(encoding="utf-8") == "My custom persona text."


def test_build_system_prompt_includes_working_memory_and_diary(tmp_path):
    cfg = Config()
    prompt = build_system_prompt(
        cfg,
        working_memory_text="remember to buy milk",
        diary_context="papik likes coffee",
        base_dir=str(tmp_path),
    )
    assert "remember to buy milk" in prompt
    assert "papik likes coffee" in prompt
    assert "<things_to_remember>" in prompt
    assert "<related_memories>" in prompt
    assert cfg.character_name in prompt


def test_build_system_prompt_omits_empty_sections(tmp_path):
    cfg = Config()
    prompt = build_system_prompt(cfg, working_memory_text="", diary_context="", base_dir=str(tmp_path))
    # The persona text itself mentions <things_to_remember> conceptually, but
    # the dynamic wrapped section (with content) must not be appended when
    # there is nothing to show.
    assert "<related_memories>" not in prompt
    assert "\n<things_to_remember>\n\n</things_to_remember>" not in prompt
