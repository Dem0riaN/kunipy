"""Tests for diary.py: file serialization round-trip and cosine similarity math."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.diary import Diary, DiaryEntry  # noqa: E402


def test_diary_entry_roundtrip():
    entry = DiaryEntry(id="entry1", body="Papik shared good news today.")
    entry.confidence = 0.5
    entry.score = 0.9

    content = entry.to_file_content()
    assert "Papik shared good news today." in content
    assert content.startswith("---\n")

    parsed = DiaryEntry.from_file_content("entry1", content)
    assert parsed.id == "entry1"
    assert parsed.body == "Papik shared good news today."
    assert parsed.confidence == 0.5
    assert parsed.score == 0.9


def test_diary_entry_from_content_without_metadata_block():
    parsed = DiaryEntry.from_file_content("entry2", "Just plain text, no metadata.")
    assert parsed.body == "Just plain text, no metadata."
    assert parsed.metadata == {}


def test_cosine_similarity_identical_vectors():
    a = np.array([1.0, 0.0, 0.0])
    sim = Diary._cosine_similarity(a, a)
    assert abs(sim - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    sim = Diary._cosine_similarity(a, b)
    assert abs(sim - 0.0) < 1e-9


def test_cosine_similarity_opposite_vectors():
    a = np.array([1.0, 0.0])
    b = np.array([-1.0, 0.0])
    sim = Diary._cosine_similarity(a, b)
    assert abs(sim - (-1.0)) < 1e-9


def test_embedding_property_roundtrip():
    entry = DiaryEntry(id="e", body="text")
    vec = np.array([0.1, 0.2, 0.3])
    entry.embedding = vec
    restored = entry.embedding
    assert restored is not None
    assert np.allclose(restored, vec)
