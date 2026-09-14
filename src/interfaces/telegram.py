"""Telegram interface protocols."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from src.domain.models import TelegramMessage


class ITelegramClient(Protocol):
    """Protocol for low-level TDLib wrapper.

    This is a thin wrapper around aiotdlib with minimal business logic.
    Implementation: TelegramClient (src/telegram_client.py)
    """

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        disable_notification: bool = False
    ) -> int:
        """Send text message via TDLib.

        Args:
            chat_id: Target chat ID
            text: Message text
            reply_to: Message ID to reply to
            disable_notification: Silent message flag

        Returns:
            Sent message ID
        """
        ...

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str
    ) -> bool:
        """Edit existing message.

        Args:
            chat_id: Target chat ID
            message_id: Message ID to edit
            text: New text

        Returns:
            True if successful
        """
        ...

    async def send_reaction(
        self,
        chat_id: int,
        message_id: int,
        reaction: str
    ) -> bool:
        """Send reaction to message.

        Args:
            chat_id: Target chat ID
            message_id: Message ID
            reaction: Reaction emoji

        Returns:
            True if successful
        """
        ...

    async def get_file_path(self, file_id: int) -> str | None:
        """Get local path of downloaded file.

        Args:
            file_id: TDLib file ID

        Returns:
            Local file path if downloaded, None otherwise
        """
        ...

    async def download_file(self, file_id: int) -> bytes | None:
        """Download file from Telegram.

        Args:
            file_id: TDLib file ID

        Returns:
            File bytes, None if failed
        """
        ...

    async def get_chat(self, chat_id: int) -> dict[str, Any] | None:
        """Get chat information.

        Args:
            chat_id: Chat ID

        Returns:
            Chat metadata
        """
        ...

    async def get_message(
        self,
        chat_id: int,
        message_id: int
    ) -> dict[str, Any] | None:
        """Get message by ID.

        Args:
            chat_id: Chat ID
            message_id: Message ID

        Returns:
            Message data, None if not found
        """
        ...

    async def get_chat_history(
        self,
        chat_id: int,
        from_message_id: int,
        limit: int
    ) -> list["TelegramMessage"]:
        """Get chat history for delivery verification.

        Args:
            chat_id: Chat ID
            from_message_id: Start from this message ID
            limit: Maximum messages to return

        Returns:
            List of messages
        """
        ...


class ITelegramMessageService(Protocol):
    """Protocol for high-level message operations.

    Builds on ITelegramClient to provide business logic like delivery tracking.
    Implementation: TelegramMessageService (src/infrastructure/telegram_message_service.py)
    """

    async def send_with_delivery_tracking(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None
    ) -> "MessageDeliveryRecord":  # noqa: F821
        """Send message with delivery verification.

        Implements ТЗ-001 punkt 12-18 delivery tracking.

        Args:
            chat_id: Target chat ID
            text: Message text
            reply_to: Message ID to reply to

        Returns:
            Delivery record for tracking
        """
        ...

    async def verify_delivery(
        self,
        chat_id: int,
        message_id: int,
        timeout_seconds: float = 10.0
    ) -> bool:
        """Check if message was delivered within timeout.

        Implements ТЗ-001 punkt 13: 10-second verification rule.

        Args:
            chat_id: Chat ID
            message_id: Message ID
            timeout_seconds: Verification timeout (default 10.0)

        Returns:
            True if delivered within timeout
        """
        ...

    async def send_with_retry(
        self,
        chat_id: int,
        text: str,
        max_retries: int = 3
    ) -> int | None:
        """Send message with automatic retry on failure.

        Args:
            chat_id: Target chat ID
            text: Message text
            max_retries: Maximum retry attempts

        Returns:
            Message ID if successful, None if all retries failed
        """
        ...
