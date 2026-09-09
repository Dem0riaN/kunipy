"""Tests for metrics.py: breadcrumb labeling and usage recording."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.metrics import breadcrumbs, record_usage, render_metrics


def test_record_usage_applies_breadcrumb_labels():
    with breadcrumbs(chat="chat_42", function="test.func"):
        record_usage(model="test-model", prompt_tokens=50, completion_tokens=10, cached_tokens=20)

    body, content_type = render_metrics()
    text = body.decode()

    assert content_type.startswith("text/plain")
    assert 'llm_usage_input_total{chat="chat_42",function="test.func",model="test-model"} ' in text
    assert 'llm_usage_output_total{chat="chat_42",function="test.func",model="test-model"} ' in text
    assert 'llm_usage_input_cache_hit_total{chat="chat_42",function="test.func",model="test-model"} ' in text
    assert 'llm_usage_input_cache_miss_total{chat="chat_42",function="test.func",model="test-model"} ' in text


def test_breadcrumbs_resets_after_block():
    with breadcrumbs(chat="chat_temp", function="temp.func"):
        pass
    # Outside the block, default ("unknown") labels should apply again.
    record_usage(model="default-model", prompt_tokens=1, completion_tokens=1)
    body, _ = render_metrics()
    text = body.decode()
    assert 'chat="unknown",function="unknown",model="default-model"' in text


def test_record_usage_without_cache_hit_only_increments_miss():
    with breadcrumbs(chat="chat_nocache", function="test.nocache"):
        record_usage(model="m", prompt_tokens=30, completion_tokens=5, cached_tokens=0)
    body, _ = render_metrics()
    text = body.decode()
    assert 'llm_usage_input_cache_miss_total{chat="chat_nocache",function="test.nocache",model="m"} 30.0' in text
