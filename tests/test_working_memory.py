"""Tests for working_memory.py: TTL expiry and disk persistence."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.working_memory import WorkingMemory  # noqa: E402


def test_set_get():
    wm = WorkingMemory()
    wm.set("foo", "bar")
    assert wm.get("foo") == "bar"


def test_ttl_expiry():
    wm = WorkingMemory()
    wm.set("temp", "value", ttl=0.01)
    assert wm.get("temp") == "value"
    time.sleep(0.05)
    assert wm.get("temp") is None


def test_no_ttl_never_expires():
    wm = WorkingMemory()
    wm.set("permanent", "value", ttl=None)
    time.sleep(0.05)
    assert wm.get("permanent") == "value"


def test_delete_and_clear():
    wm = WorkingMemory()
    wm.set("a", 1)
    wm.set("b", 2)
    wm.delete("a")
    assert wm.get("a") is None
    assert wm.get("b") == 2
    wm.clear()
    assert wm.get("b") is None


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "wm.json"
    wm = WorkingMemory()
    wm.set("things_to_remember", "call papik back", ttl=None)
    wm.set("short_lived", "x", ttl=1000)
    wm.save_to_file(str(path))
    assert path.exists()

    wm2 = WorkingMemory()
    wm2.load_from_file(str(path))
    assert wm2.get("things_to_remember") == "call papik back"
    assert wm2.get("short_lived") == "x"


def test_load_skips_expired_entries(tmp_path):
    path = tmp_path / "wm.json"
    wm = WorkingMemory()
    wm.set("expiring", "value", ttl=0.01)
    time.sleep(0.05)
    # Force-write the (already logically expired) raw entry directly, bypassing get()'s lazy cleanup.
    import json
    data = {"expiring": {"value": "value", "timestamp": wm._store["expiring"].timestamp, "ttl": 0.01}}
    path.write_text(json.dumps(data), encoding="utf-8")

    wm2 = WorkingMemory()
    wm2.load_from_file(str(path))
    assert wm2.get("expiring") is None


def test_load_from_missing_file_is_noop(tmp_path):
    wm = WorkingMemory()
    wm.load_from_file(str(tmp_path / "does_not_exist.json"))
    assert wm.get_all() == {}
