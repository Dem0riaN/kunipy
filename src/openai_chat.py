"""OpenAI-compatible LLM client for kunipy.

Provides chat completions, embeddings, and audio transcription via async HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import aiohttp
import numpy as np

from .config import EndpointAndModel, get_config

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A chat message.

    Content can be:
    - str: plain text message
    - list[dict]: multimodal content with text and images (OpenAI format)
    """
    role: str  # "system", "user", "assistant", "tool"
    content: str | list[dict] = ""
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None
    reasoning: str | None = None
    reasoning_content: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"role": self.role}
        if self.content:
            d["content"] = self.content
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.reasoning:
            d["reasoning"] = self.reasoning
        if self.reasoning_content:
            d["reasoning_content"] = self.reasoning_content
        return d


@dataclass
class ChatResponse:
    """Complete chat response."""
    id: str
    model: str
    choices: list[dict]
    usage: dict
    provider: str | None = None
    cost: float | None = None


@dataclass
class StreamingChunk:
    """A single streaming chunk from the LLM."""
    delta: dict  # role, content, tool_calls, etc.
    finish_reason: str | None = None
    usage: dict | None = None


class OpenAIChat:
    """Async client for OpenAI-compatible chat/embedding/transcription APIs."""

    def __init__(
        self,
        endpoint: EndpointAndModel | None = None,
        timeout: int = 30,
        max_retries: int = 2,
    ):
        config = get_config()
        self.endpoint = endpoint or config.llm
        self.timeout = timeout or config.request_timeout_secs
        self.max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        self._closed = False

        # Circuit breaker for service reliability (Sprint 3 Task 3)
        from .infrastructure.circuit_breaker import CircuitBreaker
        self._circuit_breaker = CircuitBreaker(
            name="openai_chat",
            failure_threshold=5,
            timeout=60.0,
        )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {"Content-Type": "application/json"}
            if self.endpoint.endpoint.bearer_key:
                headers["Authorization"] = f"Bearer {self.endpoint.endpoint.bearer_key}"
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._closed = True

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int = 8192,
        top_p: float | None = None,
        top_k: float | None = None,
        min_p: float | None = None,
        presence_penalty: float | None = None,
        repetition_penalty: float | None = None,
        seed: int | None = None,
        stream: bool = False,
    ) -> ChatResponse | AsyncIterator[StreamingChunk]:
        """Send a chat completion request with circuit breaker protection."""
        # Execute through circuit breaker (Sprint 3 Task 3)
        try:
            return await self._circuit_breaker.call(
                self._chat_impl,
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                presence_penalty=presence_penalty,
                repetition_penalty=repetition_penalty,
                seed=seed,
                stream=stream,
            )
        except RuntimeError as e:
            if "Circuit breaker" in str(e) and "OPEN" in str(e):
                logger.error(f"LLM service circuit open: {e}")
                raise RuntimeError("LLM service temporarily unavailable") from e
            raise

    async def _chat_impl(
        self,
        messages: list[Message],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int = 8192,
        top_p: float | None = None,
        top_k: float | None = None,
        min_p: float | None = None,
        presence_penalty: float | None = None,
        repetition_penalty: float | None = None,
        seed: int | None = None,
        stream: bool = False,
    ) -> ChatResponse | AsyncIterator[StreamingChunk]:
        """Internal chat implementation with retry logic."""
        config = get_config()
        if temperature is None:
            temperature = config.llm_temperature
        if top_p is None:
            top_p = config.llm_top_p
        if top_k is None:
            top_k = config.llm_top_k
        if min_p is None:
            min_p = config.llm_min_p
        if presence_penalty is None:
            presence_penalty = config.llm_presence_penalty
        if repetition_penalty is None:
            repetition_penalty = config.llm_repetition_penalty

        payload: dict = {
            "model": self.endpoint.model,
            "messages": [{"role": "system", "content": system_prompt}] + [
                m.to_dict() if hasattr(m, 'to_dict') else m for m in messages
            ],
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if top_k is not None:
            payload["top_k"] = top_k
        if min_p is not None:
            payload["min_p"] = min_p
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if repetition_penalty is not None:
            payload["repetition_penalty"] = repetition_penalty
        if seed is not None:
            payload["seed"] = seed
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        session = await self._ensure_session()
        url = self.endpoint.endpoint.base_url.rstrip("/") + "/chat/completions"

        for attempt in range(self.max_retries + 1):
            try:
                if stream:
                    # For streaming, we need to keep the response context alive
                    # Return an async generator that manages the connection lifecycle
                    return self._stream_chat(session, url, payload)
                else:
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            raise RuntimeError(f"LLM API error {resp.status}: {text}")
                        data = await resp.json()
                        parsed = self._parse_response(data)
                        self._record_usage_metrics(parsed)
                        return parsed
            except (TimeoutError, aiohttp.ClientError, RuntimeError) as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(f"LLM request failed (attempt {attempt+1}): {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("Max retries exceeded")

    async def _stream_chat(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict
    ) -> AsyncIterator[StreamingChunk]:
        """Stream chat response while keeping connection alive.

        This method manages the connection lifecycle properly by keeping
        the response context open throughout the streaming process.
        """
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"LLM API error {resp.status}: {text}")

            buffer = ""
            async for line in resp.content:
                text = line.decode("utf-8")
                buffer += text
                if not text.startswith("data: ") and text.strip():
                    continue
                if text.startswith("data: ") and text.strip() == "data: [DONE]":
                    break
                for event in buffer.split("\n\n"):
                    if not event.strip():
                        continue
                    if event.startswith("data: ") and event.strip() != "data: [DONE]":
                        try:
                            data = json.loads(event[6:])
                        except json.JSONDecodeError:
                            continue
                        if "choices" in data and len(data["choices"]) > 0:
                            choice = data["choices"][0]
                            delta = choice.get("delta", {})
                            finish = choice.get("finish_reason")
                            yield StreamingChunk(delta=delta, finish_reason=finish, usage=data.get("usage"))
                buffer = ""

    def _record_usage_metrics(self, response: ChatResponse) -> None:
        try:
            from .metrics import record_usage
        except ImportError:
            return
        try:
            usage = response.usage if isinstance(response.usage, dict) else {}
            prompt_tokens = usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or 0
            details = usage.get("prompt_tokens_details")
            cached_tokens = (details.get("cached_tokens") or 0) if isinstance(details, dict) else 0
            record_usage(
                model=response.model or self.endpoint.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.warning(f"Failed to record usage metrics: {e}")

    def _parse_response(self, data: dict) -> ChatResponse:
        return ChatResponse(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=data.get("choices", []),
            usage=data.get("usage", {}),
            provider=data.get("provider"),
            cost=data.get("cost"),
        )

    async def embedding(self, text: str, model: str | None = None) -> np.ndarray:
        """Generate embedding vector for text."""
        config = get_config()
        emb_config = config.embedding
        model_name = model or emb_config.model

        session = await self._ensure_session()
        url = emb_config.endpoint.base_url.rstrip("/") + "/embeddings"
        payload = {
            "model": model_name,
            "input": text,
        }

        for attempt in range(self.max_retries + 1):
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        text_err = await resp.text()
                        raise RuntimeError(f"Embedding API error {resp.status}: {text_err}")
                    data = await resp.json()
                    embedding = data["data"][0]["embedding"]
                    return np.array(embedding, dtype=np.float64)
            except (TimeoutError, aiohttp.ClientError, RuntimeError) as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(f"Embedding request failed (attempt {attempt+1}): {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("Max retries exceeded")


# Image processing functions moved to src/application/media/image_processor.py
# Import them for backward compatibility
from .application.media.image_processor import ImageProcessor

normalize_image_bytes = ImageProcessor.normalize_image_bytes
create_multimodal_content = ImageProcessor.create_multimodal_content

