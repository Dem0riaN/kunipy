"""Sleep-time diary consolidation service (Phase 2).

Nightly LLM-driven merge/split/prune of diary entries, following the
original C++ kuni behavior and prompts/sleep_consolidator.md:
- Pure LLM text->text transform, pieces separated by "\\n\\n---\\n\\n"
- Output amount and structure may vary (merge 2->1, split 1->2, drop)
- Confidence clamped to (-1..0.99]; never emits 1 (only out-of-band promotion)
- Entries with confidence == -1 are deleted
- Proactive merging: kNN soft limit (config.diary_knn_soft_limit)
- max_merge_span (config.diary_max_merge_span_days) bounds merge batch age spread
- Consolidated pieces are written in place under original IDs; replaced or
  dropped originals are deleted from both stores (замечание 2)

Deterministic trigger: SleepScheduler calls diary.sleep_consolidation() at
04:00 (config.sleep_chance=1.0 default, замечание 4).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .consolidation_models import ConsolidatedEntry, ConsolidationResult

if TYPE_CHECKING:
    from ...config import Config
    from ...diary import Diary, DiaryEntry
    from ...openai_chat import OpenAIChat

logger = logging.getLogger(__name__)

PIECE_SEPARATOR = "\n\n---\n\n"


class SleepConsolidationService:
    """Nightly consolidation of diary memory via sleep_consolidator.md prompt.

    Memory Independence: all vector DB access goes through Diary public API.
    """

    # Mutable entries considered per consolidation run
    MAX_ENTRIES_PER_RUN = 30
    # Upper bound of entries in a single LLM batch
    MAX_BATCH_SIZE = 8
    # Cosine similarity above which two entries are candidates for merging
    RELATEDNESS_THRESHOLD = 0.80
    # Cap on number of LLM calls per run
    MAX_BATCHES_PER_RUN = 10

    def __init__(
        self,
        diary: Diary,
        openai_chat: OpenAIChat,
        config: Config,
        prompts_dir: str | Path = "prompts",
    ):
        """Initialize consolidation service.

        Args:
            diary: Diary instance (all store access goes through it)
            openai_chat: LLM client for the consolidator call
            config: Application configuration
            prompts_dir: Directory containing sleep_consolidator.md
        """
        self._diary = diary
        self._openai = openai_chat
        self._config = config
        self._lock = asyncio.Lock()
        self._prompt = self._load_prompt(Path(prompts_dir) / "sleep_consolidator.md")

    @staticmethod
    def _load_prompt(path: Path) -> str:
        """Load the consolidator prompt; empty string if missing."""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            logger.warning(f"Consolidator prompt not found: {path}")
            return ""

    async def consolidate(self) -> ConsolidationResult:
        """Run one consolidation pass over mutable diary entries.

        Returns:
            ConsolidationResult with added/updated/deleted counts and errors.
        """
        if not self._prompt:
            msg = "sleep_consolidator.md prompt not loaded, consolidation skipped"
            logger.warning(msg)
            return ConsolidationResult(errors=[msg])

        async with self._lock:
            entries = await self._pick_entries()
            if len(entries) < 2:
                logger.info("Consolidation: not enough mutable entries")
                return ConsolidationResult()

            batches = await self._group_related(entries)
            logger.info(
                f"Consolidation: {len(entries)} entries in {len(batches)} batches"
            )

            result = ConsolidationResult()
            for batch in batches[: self.MAX_BATCHES_PER_RUN]:
                try:
                    pieces = await self._run_llm(batch)
                except Exception as e:
                    logger.exception(f"Consolidation LLM call failed for batch: {e}")
                    result.errors.append(f"llm: {e}")
                    continue

                try:
                    batch_result = await self._apply_changes(batch, pieces)
                except Exception as e:
                    logger.exception(f"Failed to apply consolidation changes: {e}")
                    result.errors.append(f"apply: {e}")
                    continue

                result.added += batch_result.added
                result.updated += batch_result.updated
                result.deleted += batch_result.deleted
                result.errors.extend(batch_result.errors)

            return result

    async def _pick_entries(self) -> list[DiaryEntry]:
        """Select mutable entries (confidence < 1), oldest first, capped."""
        all_entries = await self._diary.get_all_entries()
        mutables = [e for e in all_entries if float(e.metadata.get("confidence", 0.0)) < 1.0]
        mutables.sort(key=lambda e: int(e.metadata.get("created_at", 0)))
        return mutables[: self.MAX_ENTRIES_PER_RUN]

    async def _find_related(self, entry: DiaryEntry, n: int | None = None) -> list[DiaryEntry]:
        """Find up to n related mutable entries by vector similarity (kNN)."""
        if n is None:
            n = max(1, self._config.diary_knn_soft_limit - 1)
        embedding = entry.embedding
        if embedding is None:
            return []

        hits = await self._diary.query(embedding, max_entries=n + 5)
        related: list[DiaryEntry] = []
        for other, score in hits:
            if other.id == entry.id:
                continue
            if float(other.metadata.get("confidence", 0.0)) >= 1.0:
                continue  # anchors are read-only, never merged
            if score >= self.RELATEDNESS_THRESHOLD:
                related.append(other)
            if len(related) >= n:
                break
        return related

    async def _group_related(
        self, entries: list[DiaryEntry]
    ) -> list[list[DiaryEntry]]:
        """Union-find grouping over kNN links, respecting max_merge_span_days.

        Proactive merging: entries whose embeddings are close are batched
        together so the LLM can merge them before the kNN soft limit (5)
        is exceeded. Entries too far apart in time stay in separate batches.
        """
        by_id = {e.id: e for e in entries}
        ids = list(by_id)
        parent = {i: i for i in ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        max_span_seconds = self._config.diary_max_merge_span_days * 86400

        async def link(entry: DiaryEntry) -> None:
            related = await self._find_related(entry)
            ts_e = int(entry.metadata.get("created_at", 0))
            for other in related:
                # Guard: only union entries in our picked set
                # _find_related() can return ANY entry from ChromaDB,
                # but parent dict only contains IDs from the 30 picked entries
                if other.id not in by_id:
                    continue
                ts_o = int(other.metadata.get("created_at", 0))
                if max_span_seconds and ts_e and ts_o and abs(ts_e - ts_o) > max_span_seconds:
                    continue
                union(entry.id, other.id)

        await asyncio.gather(*(link(e) for e in entries))

        groups: dict[str, list[DiaryEntry]] = {}
        for i in ids:
            groups.setdefault(find(i), []).append(by_id[i])

        batches: list[list[DiaryEntry]] = []
        for group in groups.values():
            for start in range(0, len(group), self.MAX_BATCH_SIZE):
                chunk = group[start : start + self.MAX_BATCH_SIZE]
                if len(chunk) >= 2:
                    batches.append(chunk)
        batches.sort(key=len, reverse=True)
        return batches

    def _format_piece(self, entry: DiaryEntry) -> str:
        """Render one entry as a consolidator input piece."""
        meta = entry.metadata
        header: dict[str, Any] = {
            "confidence": float(meta.get("confidence", 0.0)),
            "kind": str(meta.get("kind", "other")),
            "importance": float(meta.get("importance", 0.5)),
        }
        tags = str(meta.get("tags", ""))
        if tags:
            header["tags"] = tags
        return f"```json\n{json_dumps_compact(header)}\n```\n\n{entry.body.strip()}"

    async def _run_llm(self, batch: list[DiaryEntry]) -> list[ConsolidatedEntry]:
        """Send a batch to the LLM and parse consolidated pieces from output."""
        from ...openai_chat import Message

        user_content = PIECE_SEPARATOR.join(self._format_piece(e) for e in batch)
        user_msg = Message(role="user", content=user_content)

        response = await self._openai.chat(
            messages=[user_msg],
            system_prompt=self._prompt,
            temperature=0.3,
            max_tokens=4000,
        )

        if not response.choices:
            return []

        content = response.choices[0].get("message", {}).get("content", "") or ""
        return self._parse_pieces(content)

    @staticmethod
    def _parse_pieces(text: str) -> list[ConsolidatedEntry]:
        """Parse LLM output into ConsolidatedEntry pieces.

        Accepts ```json fenced or bare header objects at the start of each
        piece; ignores the surrounding fence formatting when present.
        """
        import json

        pieces: list[ConsolidatedEntry] = []
        raw_parts = re.split(r"^-{3,}$", text, flags=re.MULTILINE)
        header_re = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

        for part in raw_parts:
            part = part.strip()
            if not part:
                continue
            header: dict[str, Any] = {}
            m = header_re.search(part)
            if m:
                try:
                    header = json.loads(m.group(1))
                except json.JSONDecodeError:
                    header = {}
                part = (part[: m.start()] + part[m.end():]).strip()
            if not part:
                continue  # header-only fragment (e.g. trailing fence remnant)

            try:
                confidence = float(header.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            # Consolidator must never emit 1 (out-of-band promotion only)
            confidence = max(-1.0, min(0.99, confidence))

            def _str_list(key: str, header=header) -> list[str]:
                v = header.get(key) or []
                if isinstance(v, str):
                    v = [t for t in re.split(r"[,;]", v) if t.strip()]
                return [str(x).strip() for x in v if str(x).strip()]

            try:
                importance = float(header.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5

            kind = str(header.get("kind", "other")).lower()
            if kind not in ("entity_description", "thought", "event", "fact", "other"):
                kind = "other"

            pieces.append(
                ConsolidatedEntry(
                    body=part,
                    confidence=confidence,
                    rationale=str(header.get("rationale", "")),
                    kind=kind,
                    retrieval_cues=_str_list("retrieval_cues"),
                    entities=_str_list("entities"),
                    tags=_str_list("tags"),
                    importance=importance,
                    created_at=int(time.time()),
                )
            )
        return pieces

    async def _apply_changes(
        self, batch: list[DiaryEntry], pieces: list[ConsolidatedEntry]
    ) -> ConsolidationResult:
        """Write consolidated pieces back and drop replaced originals.

        Mapping heuristic: piece i updates original entry i in place (same ID,
        fresh embedding). Extra pieces (splits) are added under fresh Unix
        timestamp IDs. Originals with no corresponding piece (merged/dropped)
        are deleted from both stores (замечание 2). Pieces with confidence == -1
        are not written; their original slot is deleted.
        """
        result = ConsolidationResult()
        if not pieces:
            # Empty or unparseable output: leave the diary untouched rather
            # than destroy data. The next nightly run will retry this batch.
            result.errors.append("empty LLM output, batch left untouched")
            return result

        for i, piece in enumerate(pieces):
            original = batch[i] if i < len(batch) else None
            target_id = original.id if original else str(int(time.time()) + i)

            if piece.confidence <= -1.0:
                if original:
                    await self._diary.delete_entry(original.id)
                    result.deleted += 1
                continue

            if original:
                result.updated += 1
            else:
                result.added += 1

            embedding = await self._diary._get_embedding(piece.body)
            meta: dict[str, Any] = {
                "score": float(original.metadata.get("score", 0.0)) if original else 0.0,
                "confidence": piece.confidence,
                "lastUsed": str(
                    original.metadata.get("lastUsed", "never") if original else "never"
                ),
                "usageCount": int(
                    original.metadata.get("usageCount", 0) if original else 0
                ),
                "importance": piece.importance,
                "kind": piece.kind,
                "tags": ",".join(piece.tags),
                "retrieval_cues": ",".join(piece.retrieval_cues),
                "rationale": piece.rationale,
                "visibility": str(
                    original.metadata.get("visibility", "global") if original else "global"
                ),
                "user_id": str(original.metadata.get("user_id", "") if original else ""),
                "chat_id": str(original.metadata.get("chat_id", "") if original else ""),
                "sourceChannel": str(
                    original.metadata.get("sourceChannel", "consolidation") if original
                    else "consolidation"
                ),
                "created_at": int(
                    original.metadata.get("created_at", piece.created_at) if original
                    else piece.created_at
                ),
                "consolidated_at": piece.created_at,
            }
            if original:
                src_ts = original.metadata.get("source_timestamp", original.id)
                meta["source_timestamp"] = str(src_ts)

            from ...diary import DiaryEntry

            entry = DiaryEntry(id=target_id, body=piece.body, metadata=meta)
            entry.embedding = np.asarray(embedding, dtype=np.float64)
            await self._diary.save(entry)

        # Originals replaced by merges: no corresponding output piece -> delete
        for j in range(len(pieces), len(batch)):
            await self._diary.delete_entry(batch[j].id)
            result.deleted += 1

        return result


def json_dumps_compact(obj: Any) -> str:
    """Compact single-line JSON without external import at module level."""
    import json

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
