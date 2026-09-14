"""Architecture tests: interface compliance.

Verifies that implementations comply with their interface protocols.
"""

from typing import get_type_hints


class TestInterfaceCompliance:
    """Test that concrete implementations comply with their protocols."""

    def test_openai_chat_implements_interface(self):
        """OpenAIChat must implement IOpenAIChat protocol.

        ТЗ-001 punkt 8: All implementations must match their interfaces.
        """
        from src.openai_chat import OpenAIChat

        # Check that required methods exist
        required_methods = ["chat", "embedding"]

        for method_name in required_methods:
            assert hasattr(OpenAIChat, method_name), (
                f"OpenAIChat missing required method: {method_name}"
            )

            # Check method is callable
            method = getattr(OpenAIChat, method_name)
            assert callable(method), (
                f"OpenAIChat.{method_name} is not callable"
            )

    def test_telegram_client_implements_interface(self):
        """TelegramClient must implement ITelegramClient protocol.

        ТЗ-001 punkt 8: All implementations must match their interfaces.
        """
        from src.telegram_client import TelegramClient

        # Check that required methods exist
        required_methods = [
            "send_message",
            "edit_message",
            "get_file_path",
            "download_file",
        ]

        for method_name in required_methods:
            assert hasattr(TelegramClient, method_name), (
                f"TelegramClient missing required method: {method_name}"
            )

            method = getattr(TelegramClient, method_name)
            assert callable(method), (
                f"TelegramClient.{method_name} is not callable"
            )

    def test_protocols_are_properly_defined(self):
        """All protocols in interfaces/ should use typing.Protocol.

        ТЗ-001 punkt 8: Use Protocol for structural subtyping.
        """
        from src.interfaces import (
            IMemoryStore,
            IMessageDeliveryTracker,
            IOpenAIChat,
            ITelegramClient,
        )

        protocols = [
            IOpenAIChat,
            ITelegramClient,
            IMemoryStore,
            IMessageDeliveryTracker,
        ]

        for protocol in protocols:
            # Protocol classes have _is_protocol attribute
            assert hasattr(protocol, '_is_protocol'), (
                f"{protocol.__name__} should be a Protocol"
            )

    def test_di_container_has_all_required_dependencies(self):
        """Dependencies container must have all core interfaces.

        ТЗ-001 punkt 9: DI container must provide all dependencies.
        """
        from src.di import Dependencies

        required_fields = [
            "config",
            "openai_chat",
            "telegram_client",
            "memory_store",
            "delivery_tracker",
            "notification_manager",
        ]

        # Get type hints (fields) from dataclass
        hints = get_type_hints(Dependencies)

        for field_name in required_fields:
            assert field_name in hints, (
                f"Dependencies missing required field: {field_name}"
            )

    def test_stub_implementations_exist_for_phase_2(self):
        """Stub implementations must exist for Phase 2 features.

        ТЗ-001 punkt 73: Phase 1 provides stubs for Phase 2 implementation.
        """
        # Memory stubs (ТЗ-002)
        # Delivery tracking stub
        from src.infrastructure.delivery.stub_tracker import StubDeliveryTracker
        from src.infrastructure.memory.stub_store import InMemoryStore, InMemoryWorkingMemory

        # Worker stub
        from src.infrastructure.worker.stub_notification_manager import StubNotificationManager

        # All stubs should instantiate without errors
        memory_store = InMemoryStore()
        working_memory = InMemoryWorkingMemory()
        delivery_tracker = StubDeliveryTracker()
        notification_manager = StubNotificationManager()

        assert memory_store is not None
        assert working_memory is not None
        assert delivery_tracker is not None
        assert notification_manager is not None
