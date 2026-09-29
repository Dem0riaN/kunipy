"""Media generation tools for LLM function calling.

Provides tools for generating images (Stable Diffusion), audio/voice (TTS), and stickers.
"""

import logging
import time
from pathlib import Path
from typing import Any

from ...config import get_config
from ...openai_chat import OpenAIChat
from ...telegram_client import TelegramChat, TelegramClient
from .registry import Tool, ToolContext

logger = logging.getLogger(__name__)


def register_media_tools(
    registry: Any,
    telegram: TelegramClient,
    openai: OpenAIChat,
    current_chat: TelegramChat | None = None,
) -> None:
    """Register media generation tools.

    Args:
        registry: ToolRegistry instance
        telegram: Telegram client
        openai: OpenAI client for TTS
        current_chat: Current chat context
    """
    config = get_config()

    # Take photo tool (image generation)
    if config.capability_take_photo:
        async def _take_photo(ctx: ToolContext) -> str:
            from ...image_generator import get_image_generator

            chat_id = ctx.args.get("chat_id") or (current_chat.id if current_chat else 0)
            generator = get_image_generator()
            path = await generator.generate_and_save(
                prompt=ctx.args["prompt"],
                negative_prompt=ctx.args.get("negative_prompt", ""),
                width=ctx.args.get("width", 512),
                height=ctx.args.get("height", 512),
            )
            if not path:
                return "Error: image generation failed or is disabled."
            if chat_id:
                await telegram.send_photo(chat_id, path, caption=ctx.args["prompt"][:1000])
                return f"Photo generated and sent ({path})."
            return f"Photo generated at {path} (no chat to send to)."

        registry.register(
            name="take_photo",
            tool=Tool(
                type="function",
                function={
                    "name": "take_photo",
                    "description": "Generate a photo/image using AI (Stable Diffusion) and send it to the chat.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "Description of the image to generate"},
                            "negative_prompt": {"type": "string", "description": "What to avoid in the image"},
                            "width": {"type": "integer", "description": "Image width in pixels", "default": 512},
                            "height": {"type": "integer", "description": "Image height in pixels", "default": 512},
                            "chat_id": {"type": "integer", "description": "Optional: target chat ID"},
                        },
                        "required": ["prompt"],
                    },
                },
            ),
            handler=_take_photo,
        )

    # Record audio tool (TTS)
    if config.capability_record_voice:
        async def _record_audio(ctx: ToolContext) -> str:
            chat_id = ctx.args.get("chat_id") or (current_chat.id if current_chat else 0)
            audio = await openai.synthesize_speech(ctx.args["text"], voice=ctx.args.get("voice"))
            if not audio:
                return "Error: text-to-speech failed or is disabled."

            ext = "mp3" if config.record_voice_backend.value == "elevenlabs" else config.record_voice_openai_format
            out_dir = Path("data/generated_audio")
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{int(time.time() * 1000)}.{ext}"
            path.write_bytes(audio)

            if chat_id:
                await telegram.send_voice(chat_id, str(path), caption=ctx.args["text"][:200])
                return f"Voice message generated and sent ({path})."
            return f"Voice message generated at {path} (no chat to send to)."

        registry.register(
            name="record_audio",
            tool=Tool(
                type="function",
                function={
                    "name": "record_audio",
                    "description": "Record and send a voice message (text-to-speech).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "The text to speak"},
                            "voice": {"type": "string", "description": "Voice name or ID (optional)"},
                            "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
                        },
                        "required": ["text"],
                    },
                },
            ),
            handler=_record_audio,
        )

    # Sticker tools
    if config.capability_use_stickers:
        async def _sticker_send(ctx: ToolContext) -> str:
            chat_id = ctx.args.get("chat_id") or (current_chat.id if current_chat else 0)
            if not chat_id:
                return "Error: no chat_id available to send the sticker to."
            await telegram.send_sticker(chat_id, ctx.args["sticker"])
            return f"Sticker {ctx.args['sticker']} sent."

        registry.register(
            name="sticker_send",
            tool=Tool(
                type="function",
                function={
                    "name": "sticker_send",
                    "description": "Send a sticker (by its Telegram file_id) to the current chat.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sticker": {"type": "string", "description": "Sticker file_id (see sticker_list)"},
                            "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
                        },
                        "required": ["sticker"],
                    },
                },
            ),
            handler=_sticker_send,
        )

        async def _sticker_list(ctx: ToolContext) -> str:
            stickers = await telegram.get_stickers(limit=ctx.args.get("limit", 20))
            if not stickers:
                return "You have no saved stickers yet."
            lines = [f"{s['emoji'] or '?'} -> file_id={s['file_id']}" for s in stickers if s.get("file_id")]
            return "Your stickers:\n" + "\n".join(lines) if lines else "You have no saved stickers yet."

        registry.register(
            name="sticker_list",
            tool=Tool(
                type="function",
                function={
                    "name": "sticker_list",
                    "description": "List your favorite/recently used stickers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum number of stickers to list", "default": 20},
                        },
                    },
                },
            ),
            handler=_sticker_list,
        )

        async def _sticker_save(ctx: ToolContext) -> str:
            ok = await telegram.save_sticker(ctx.args["sticker_id"])
            return f"Sticker {ctx.args['sticker_id']} saved." if ok else f"Failed to save sticker {ctx.args['sticker_id']}."

        registry.register(
            name="sticker_save",
            tool=Tool(
                type="function",
                function={
                    "name": "sticker_save",
                    "description": "Save a sticker to your favorites.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sticker_id": {"type": "string", "description": "The sticker file ID to save"},
                        },
                        "required": ["sticker_id"],
                    },
                },
            ),
            handler=_sticker_save,
        )
