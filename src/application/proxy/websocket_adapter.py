"""WebSocket adapter for Open-LLM-VTuber integration.

Implements WebSocket protocol adapter for real-time bidirectional streaming.
Following ТЗ-001 §54 - Infrastructure layer adapter.
Architecture: Adapter pattern for protocol bridging.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from .core.service import ProxyCoreService

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """Queued WebSocket message awaiting processing.

    Following ТЗ-001 §10 - Typed domain models.
    """
    message_type: str
    data: dict
    timestamp: float


class WebSocketProxyAdapter:
    """WebSocket adapter for Open-LLM-VTuber integration.

    Responsibilities (ТЗ-001 §54 - Infrastructure layer):
    - WebSocket protocol handling
    - Message queue with conversation_active flag
    - Bidirectional streaming
    - Protocol translation (WebSocket ↔ ProxyCoreService)

    Architecture:
    - Adapter pattern: translates WebSocket protocol to core service calls
    - Producer-consumer: message queue prevents race conditions
    - State machine: conversation_active flag

    Open-LLM-VTuber protocol:
    - Client → Server: text-input, interrupt-signal, request-init-config
    - Server → Client: user-input-transcription, llm-sentence, control
    """

    def __init__(self, core_service: ProxyCoreService, user_id: str = "vtuber_user"):
        """Initialize WebSocket adapter.

        Args:
            core_service: Protocol-agnostic core service (ТЗ-001 §8 - DI)
            user_id: User identifier for session tracking
        """
        self._core = core_service
        self._user_id = user_id
        self._message_queue: deque[QueuedMessage] = deque()
        self._conversation_active = False
        self._websocket: WebSocket | None = None
        self._consumer_task: asyncio.Task | None = None
        logger.info(f"WebSocketProxyAdapter initialized for user {user_id}")

    async def handle_connection(self, websocket: WebSocket) -> None:
        """Handle WebSocket connection lifecycle.

        Main entry point for WebSocket connections.
        Manages connection, message routing, and cleanup.

        Args:
            websocket: FastAPI WebSocket connection
        """
        await websocket.accept()
        self._websocket = websocket
        logger.info(f"WebSocket connection accepted for user {self._user_id}")

        # Start background consumer
        self._consumer_task = asyncio.create_task(self._consumer_loop())

        try:
            # Message receive loop
            while True:
                data = await websocket.receive_text()
                await self._handle_incoming_message(data)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {self._user_id}")
        except Exception:
            logger.exception(f"Error in WebSocket connection for user {self._user_id}")
        finally:
            await self._cleanup()

    async def _handle_incoming_message(self, raw_data: str) -> None:
        """Handle incoming WebSocket message.

        Routes message to appropriate handler based on type.

        Args:
            raw_data: Raw JSON string from WebSocket
        """
        try:
            data = json.loads(raw_data)
            message_type = data.get("type", "")

            logger.debug(f"Received WebSocket message: type={message_type}")

            if message_type == "text-input":
                await self._handle_text_input(data)
            elif message_type == "interrupt-signal":
                await self._handle_interrupt()
            elif message_type == "request-init-config":
                await self._handle_init_config(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {raw_data[:100]}")
        except Exception:
            logger.exception("Error handling incoming message")

    async def _handle_text_input(self, data: dict) -> None:
        """Handle text-input message from client.

        Queues message for processing if conversation is idle.
        Implements producer-consumer pattern to prevent race conditions.

        Args:
            data: Message data with 'text' field
        """
        text = data.get("text", "")
        if not text:
            logger.warning("Received text-input with empty text")
            return

        # Queue message
        import time
        queued = QueuedMessage(
            message_type="text-input",
            data=data,
            timestamp=time.time()
        )
        self._message_queue.append(queued)
        logger.info(f"Queued text-input: '{text[:50]}...' (queue size: {len(self._message_queue)})")

    async def _handle_interrupt(self) -> None:
        """Handle interrupt-signal from client.

        Interrupts current conversation and marks session as interrupted.
        """
        logger.info("Received interrupt-signal")

        # Clear message queue
        self._message_queue.clear()

        # Mark conversation as idle
        self._conversation_active = False

        # Send control message
        if self._websocket:
            await self._send_control("conversation-interrupted")

    async def _handle_init_config(self, data: dict) -> None:
        """Handle request-init-config from client.

        Sends initial configuration to client.

        Args:
            data: Request data
        """
        logger.debug("Received request-init-config")

        # Send config response
        if self._websocket:
            config = {
                "type": "init-config",
                "config": {
                    "server_name": "kunipy-proxy",
                    "version": "1.0.0",
                    "capabilities": ["text-input", "interrupt-signal"]
                }
            }
            await self._websocket.send_text(json.dumps(config, ensure_ascii=False))

    async def _consumer_loop(self) -> None:
        """Background consumer for queued messages.

        Processes messages from queue when conversation is idle.
        Implements producer-consumer pattern.
        """
        logger.info("Consumer loop started")

        try:
            while True:
                # Check if we can process next message
                if not self._conversation_active and len(self._message_queue) > 0:
                    message = self._message_queue.popleft()
                    await self._process_message(message)

                # Sleep to prevent busy loop
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled")
        except Exception:
            logger.exception("Error in consumer loop")

    async def _process_message(self, message: QueuedMessage) -> None:
        """Process queued message through core service.

        Main processing pipeline: message → core service → streaming response.

        Args:
            message: Queued message to process
        """
        try:
            # Mark conversation as active
            self._conversation_active = True
            logger.info(f"Processing message: {message.message_type}")

            # Extract text
            text = message.data.get("text", "")

            # Process through core service
            response_text = await self._core.process_user_message(
                user_id=self._user_id,
                text=text,
                headers={"X-Papik-Auth": "true"}
            )

            # CRITICAL DEBUG: Log exact response with repr()
            logger.error(f"[WEBSOCKET] Raw response from core: {response_text!r}")
            logger.error(f"[WEBSOCKET] Response starts with curly brace: {response_text.strip().startswith('{')}")
            logger.error(f"[WEBSOCKET] Response contains 'thinking': {'thinking' in response_text}")

            # Check if response is empty
            if not response_text or not response_text.strip():
                logger.warning("Empty response from core service - LLM may have put everything in 'thinking'")
                response_text = "..."  # Fallback

            # Check if response still contains JSON structure (filter didn't work)
            if response_text.strip().startswith("{") and '"thinking"' in response_text:
                logger.error(f"JSON leaked to user output! Raw response: {response_text}")
                # Emergency fallback: try to extract response field manually
                try:
                    import json
                    data = json.loads(response_text)
                    extracted = data.get("response", "")
                    if extracted and extracted.strip():
                        logger.warning("Extracted response field from leaked JSON")
                        response_text = extracted
                    else:
                        logger.error("Response field empty in leaked JSON, using fallback")
                        response_text = "..."
                except Exception as e:
                    logger.error(f"Failed to parse leaked JSON: {e}, using fallback")
                    response_text = "..."

            # Send llm-sentence chunks
            # TODO Phase 2.4: Implement true streaming with sentence segmentation
            await self._send_sentence(response_text, "")

            # Send conversation end
            await self._send_control("conversation-chain-end")

        except Exception:
            logger.exception("Error processing message")
            # Send error response
            await self._send_sentence("Sorry, an error occurred while processing your message.", "")
            await self._send_control("conversation-chain-end")
        finally:
            # Mark conversation as idle
            self._conversation_active = False
            logger.info("Conversation marked as idle")

    async def _send_sentence(self, text: str, audio: str = "") -> None:
        """Send llm-sentence message to client.

        Args:
            text: Sentence text
            audio: Base64 encoded audio (optional)
        """
        if not self._websocket:
            return

        message = {
            "type": "llm-sentence",
            "text": text,
            "audio": audio
        }
        await self._websocket.send_text(json.dumps(message, ensure_ascii=False))

    async def _send_control(self, control_type: str) -> None:
        """Send control message to client.

        Args:
            control_type: Control message type (e.g., 'conversation-chain-end')
        """
        if not self._websocket:
            return

        message = {
            "type": "control",
            "text": control_type
        }
        await self._websocket.send_text(json.dumps(message, ensure_ascii=False))

    async def _cleanup(self) -> None:
        """Cleanup resources on connection close."""
        logger.info("Cleaning up WebSocket connection")

        # Cancel consumer task
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # Clear queue
        self._message_queue.clear()

        # Reset state
        self._conversation_active = False
        self._websocket = None
