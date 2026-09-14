"""Data models for sleep consolidation (Phase 2).

ConsolidatedEntry and ConsolidationResult — outputs of nightly LLM-based
diary consolidation following C++ kuni sleep_consolidator.md prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsolidatedEntry:
    """A single consolidated diary entry.

    Output of sleep consolidation LLM call.
    Confidence is clamped to (-1..0.99] per sleep_consolidator.md:
    "Never set confidence to 1."
    """

    body: str
    confidence: float  # -1 to 0.99 (never 1 per consolidator policy)
    rationale: str = ""
    kind: str = "other"  # entity_description, thought, event, fact, other
    retrieval_cues: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    created_at: int = 0  # Unix timestamp — fresh at consolidation time


@dataclass
class ConsolidationResult:
    """Summary of a consolidation run."""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)
