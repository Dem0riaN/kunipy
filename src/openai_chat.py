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
        """Send a chat completion request."""
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
            "messages": [{"role": "system", "content": system_prompt}] + [m.to_dict() for m in messages],
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
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"LLM API error {resp.status}: {text}")
                    if stream:
                        return self._stream_response(resp)
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

    async def _stream_response(self, resp: aiohttp.ClientResponse) -> AsyncIterator[StreamingChunk]:
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


def normalize_image_bytes(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Normalize image bytes to PNG or JPEG format.

    Handles WebP decoding and ensures the image is in a format compatible
    with OpenAI vision models. Conversion happens entirely in memory.

    Args:
        image_data: Raw image bytes (any format Pillow supports)
        mime_type: Original MIME type (e.g., "image/webp", "image/jpeg")

    Returns:
        Tuple of (normalized_bytes, normalized_mime_type)
        - For images with transparency: PNG
        - For images without transparency: JPEG (smaller size)

    Raises:
        RuntimeError: If image cannot be decoded
    """
    try:
        from io import BytesIO

        from PIL import Image

        # Decode image
        img = Image.open(BytesIO(image_data))

        # Determine output format based on transparency
        has_alpha = img.mode in ("RGBA", "LA", "P") and (
            img.mode == "P" and "transparency" in img.info or img.mode in ("RGBA", "LA")
        )

        output = BytesIO()
        if has_alpha:
            # Preserve transparency with PNG
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(output, format="PNG", optimize=True)
            return output.getvalue(), "image/png"
        else:
            # Convert to JPEG for better compression
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue(), "image/jpeg"
    except Exception as e:
        logger.error(f"Failed to normalize image: {e}")
        raise RuntimeError(f"Image normalization failed: {e}") from e


def create_multimodal_content(text: str, image_data: bytes, mime_type: str) -> list[dict]:
    """Create OpenAI-compatible multimodal content with text and image.

    Args:
        text: Text content (can be empty)
        image_data: Image bytes
        mime_type: Image MIME type

    Returns:
        List of content parts in OpenAI format:
        [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:..."}}
        ]
    """
    import base64

    # Normalize image format if needed
    if mime_type == "image/webp" or mime_type not in ("image/jpeg", "image/png"):
        image_data, mime_type = normalize_image_bytes(image_data, mime_type)

    b64 = base64.b64encode(image_data).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"

    content_parts = []
    if text:
        content_parts.append({"type": "text", "text": text})
    content_parts.append({"type": "image_url", "image_url": {"url": data_url}})

    return content_parts


    async def _stream_response(self, resp: aiohttp.ClientResponse) -> AsyncIterator[StreamingChunk]:
        buffer = ""
        async for line in resp.content:
            text = line.decode("utf-8")
            buffer += text
            if not text.startswith("data: ") and text.strip():
                continue
            if text.startswith("data: ") and text.strip() == "data: [DONE]":
                break
            # handle partial lines (SSE can have multiple events per chunk)
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
        """Record token usage from a completed chat response, if the
        `metrics` module (prometheus_client) is available.

        Best-effort: some OpenAI-compatible servers (notably local ones)
        send `"prompt_tokens_details": null` explicitly rather than omitting
        the key, so `.get(key, {})` alone isn't enough -- `.get` only falls
        back to the default when the key is *absent*, not when its value is
        `None`. Any failure here is logged and swallowed rather than
        breaking the actual LLM response path.
        """
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

