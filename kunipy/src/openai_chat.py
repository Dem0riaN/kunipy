"""OpenAI-compatible LLM client for kunipy.

Provides chat completions, embeddings, and audio transcription via async HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Dict, List, Union

import aiohttp
import numpy as np

from .config import EndpointAndModel, get_config

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[dict]] = None
    reasoning: Optional[str] = None
    reasoning_content: Optional[str] = None

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
    choices: List[dict]
    usage: dict
    provider: Optional[str] = None
    cost: Optional[float] = None


@dataclass
class StreamingChunk:
    """A single streaming chunk from the LLM."""
    delta: dict  # role, content, tool_calls, etc.
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None


class OpenAIChat:
    """Async client for OpenAI-compatible chat/embedding/transcription APIs."""

    def __init__(
        self,
        endpoint: Optional[EndpointAndModel] = None,
        timeout: int = 30,
        max_retries: int = 2,
    ):
        config = get_config()
        self.endpoint = endpoint or config.llm
        self.timeout = timeout or config.request_timeout_secs
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
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
        messages: List[Message],
        system_prompt: str = "",
        tools: Optional[List[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 8192,
        top_p: Optional[float] = None,
        top_k: Optional[float] = None,
        min_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        repetition_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        stream: bool = False,
    ) -> Union[ChatResponse, AsyncIterator[StreamingChunk]]:
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
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
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
        `metrics` module (prometheus_client) is available."""
        try:
            from .metrics import record_usage
        except ImportError:
            return
        usage = response.usage or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) or 0
        record_usage(
            model=response.model or self.endpoint.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )

    def _parse_response(self, data: dict) -> ChatResponse:
        return ChatResponse(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=data.get("choices", []),
            usage=data.get("usage", {}),
            provider=data.get("provider"),
            cost=data.get("cost"),
        )

    async def embedding(self, text: str, model: Optional[str] = None) -> np.ndarray:
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
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(f"Embedding request failed (attempt {attempt+1}): {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("Max retries exceeded")

    async def synthesize_speech(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        """Synthesize speech (TTS) from text, using the configured backend.

        Supports ElevenLabs and OpenAI-compatible `/audio/speech` endpoints,
        selected via `config.record_voice_backend`. Returns audio bytes
        (format depends on the backend / configured response format), or
        None if TTS is disabled or the request fails.
        """
        config = get_config()
        if not config.capability_record_voice:
            logger.warning("Voice recording (TTS) disabled in config")
            return None

        session = await self._ensure_session()
        backend = config.record_voice_backend.value

        try:
            if backend == "elevenlabs":
                voice_id = voice or config.record_voice_elevenlabs_voice
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                headers = {
                    "xi-api-key": config.record_voice_elevenlabs_key,
                    "Content-Type": "application/json",
                }
                payload = {
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        raise RuntimeError(f"ElevenLabs TTS error {resp.status}: {err}")
                    return await resp.read()

            elif backend == "openai":
                url = config.record_voice_openai_url.rstrip("/") + "/audio/speech"
                headers = {"Content-Type": "application/json"}
                if config.record_voice_openai_key:
                    headers["Authorization"] = f"Bearer {config.record_voice_openai_key}"
                payload = {
                    "model": config.record_voice_openai_model,
                    "input": text,
                    "voice": voice or config.record_voice_openai_voice,
                    "response_format": config.record_voice_openai_format,
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        raise RuntimeError(f"OpenAI-compatible TTS error {resp.status}: {err}")
                    return await resp.read()

            else:
                logger.error(f"Unknown TTS backend: {backend}")
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
            logger.error(f"TTS request failed: {e}")
            return None

    async def describe_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: str = "Describe this image in detail, in a few sentences.",
        cheap: bool = False,
    ) -> str:
        """Describe an image using a vision-capable chat model.

        Uses `llm_image_to_text_cheap` when `cheap=True` (e.g. for a quick
        glance at a sticker/reaction image), otherwise `llm_image_to_text`.
        """
        config = get_config()
        vision_config = config.llm_image_to_text_cheap if cheap else config.llm_image_to_text
        if not vision_config.endpoint.base_url:
            logger.warning("No vision endpoint configured, skipping image description")
            return ""

        import base64
        b64 = base64.b64encode(image_data).decode("ascii")

        session = await self._ensure_session()
        url = vision_config.endpoint.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if vision_config.endpoint.bearer_key:
            headers["Authorization"] = f"Bearer {vision_config.endpoint.bearer_key}"

        payload = {
            "model": vision_config.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }],
        }

        for attempt in range(self.max_retries + 1):
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        text_err = await resp.text()
                        raise RuntimeError(f"Vision API error {resp.status}: {text_err}")
                    data = await resp.json()
                    parsed = self._parse_response(data)
                    self._record_usage_metrics(parsed)
                    if parsed.choices:
                        return parsed.choices[0].get("message", {}).get("content", "") or ""
                    return ""
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(f"Vision request failed (attempt {attempt+1}): {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("Max retries exceeded")

    async def transcribe_audio(self, audio_data: bytes, format: str = "ogg") -> str:
        """Transcribe audio to text using Whisper-compatible API."""
        config = get_config()
        audio_config = config.llm_audio_to_text

        session = await self._ensure_session()
        url = audio_config.endpoint.base_url.rstrip("/") + "/audio/transcriptions"

        # Build multipart form
        data = aiohttp.FormData()
        data.add_field("file", audio_data, filename=f"audio.{format}", content_type=f"audio/{format}")
        data.add_field("model", audio_config.model)
        data.add_field("response_format", "json")

        headers = {}
        if audio_config.endpoint.bearer_key:
            headers["Authorization"] = f"Bearer {audio_config.endpoint.bearer_key}"

        for attempt in range(self.max_retries + 1):
            try:
                async with session.post(url, data=data, headers=headers) as resp:
                    if resp.status != 200:
                        text_err = await resp.text()
                        raise RuntimeError(f"Transcription API error {resp.status}: {text_err}")
                    result = await resp.json()
                    return result.get("text", "")
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(f"Transcription request failed (attempt {attempt+1}): {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("Max retries exceeded")
