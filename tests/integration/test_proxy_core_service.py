"""Integration test for ProxyCoreService.

Tests full message processing pipeline with mocked dependencies.
Following ТЗ-001 §66 - Integration tests.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.application.proxy.core.models import FilteredResponse, UserContext
from src.application.proxy.core.service import ProxyCoreService
from src.openai_chat import Message


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = Mock()
    config.papik_chat_id = "123456"
    config.papik_name = "Test Papik"
    config.diary_auto_rag_enabled = False
    config.proxy_upstream = Mock()
    config.proxy_upstream.endpoint.base_url = ""
    config.llm = Mock()
    config.llm.endpoint.base_url = "http://localhost:11434/v1/"
    return config


@pytest.fixture
def mock_dependencies():
    """Mock all ProxyCoreService dependencies."""
    deps = {
        "session_manager": Mock(),
        "message_injector": Mock(),
        "tool_provider": Mock(),
        "context_manager": Mock(),
        "thinking_filter": Mock(),
        "diary_injector": None,
    }

    # Setup session manager
    deps["session_manager"].calculate_fingerprint = Mock(return_value="test_session_id")

    # Setup message injector
    deps["message_injector"].merge_hidden_context = Mock(return_value=[])
    deps["message_injector"].store_hidden_messages = Mock()

    # Setup tool provider
    deps["tool_provider"].get_tool_schemas = Mock(return_value=None)
    deps["tool_provider"].execute_tool_calls = AsyncMock(return_value=[])

    # Setup context manager
    deps["context_manager"].resolve_user_context = AsyncMock(
        return_value=UserContext(
            user_id="test_user",
            is_papik=True,
            telegram_id="123456",
            linked_user_ids=["123456"],
            working_memory="Test working memory",
            display_name="Test Papik"
        )
    )
    deps["context_manager"].build_system_prompt = Mock(
        return_value="Test system prompt"
    )

    # Setup thinking filter
    deps["thinking_filter"].filter_response = Mock(
        return_value=FilteredResponse(
            content="Filtered response",
            thinking="Internal thinking",
            emotion="neutral"
        )
    )

    return deps


@pytest.fixture
def core_service(mock_config, mock_dependencies):
    """Create ProxyCoreService with mocked dependencies."""
    return ProxyCoreService(
        config=mock_config,
        session_manager=mock_dependencies["session_manager"],
        message_injector=mock_dependencies["message_injector"],
        tool_provider=mock_dependencies["tool_provider"],
        context_manager=mock_dependencies["context_manager"],
        thinking_filter=mock_dependencies["thinking_filter"],
        diary_injector=mock_dependencies["diary_injector"],
    )


class TestProxyCoreServiceIntegration:
    """Integration tests for ProxyCoreService."""

    @pytest.mark.asyncio
    async def test_resolve_user_context_delegates_to_context_manager(
        self, core_service, mock_dependencies
    ):
        """Test user context resolution delegates correctly."""
        # Act
        result = await core_service.resolve_user_context(
            user_id="test_user",
            headers={"X-Papik-Auth": "true"}
        )

        # Assert
        assert result.user_id == "test_user"
        assert result.is_papik is True
        mock_dependencies["context_manager"].resolve_user_context.assert_called_once()

    def test_build_system_prompt_delegates_to_context_manager(
        self, core_service, mock_dependencies
    ):
        """Test system prompt building delegates correctly."""
        # Arrange
        user_context = UserContext(
            user_id="test_user",
            is_papik=True,
            telegram_id="123456",
            linked_user_ids=["123456"],
            working_memory="Test memory",
            display_name="Test Papik"
        )

        # Act
        result = core_service.build_system_prompt(user_context, "Diary context")

        # Assert
        assert result == "Test system prompt"
        mock_dependencies["context_manager"].build_system_prompt.assert_called_once_with(
            user_context, "Diary context"
        )

    def test_filter_response_delegates_to_thinking_filter(
        self, core_service, mock_dependencies
    ):
        """Test response filtering delegates correctly."""
        # Act
        result = core_service.filter_response("Test response with thinking")

        # Assert
        assert result.content == "Filtered response"
        assert result.thinking == "Internal thinking"
        mock_dependencies["thinking_filter"].filter_response.assert_called_once()

    def test_merge_hidden_context_delegates_to_message_injector(
        self, core_service, mock_dependencies
    ):
        """Test hidden context merging delegates correctly."""
        # Arrange
        messages = [Message(role="user", content="Hello")]

        # Act
        core_service.merge_hidden_context(messages, "session_123")

        # Assert
        mock_dependencies["message_injector"].merge_hidden_context.assert_called_once_with(
            messages, "session_123"
        )

    def test_store_hidden_messages_delegates_to_message_injector(
        self, core_service, mock_dependencies
    ):
        """Test hidden message storage delegates correctly."""
        # Arrange
        messages = [Message(role="assistant", content="Response")]

        # Act
        core_service.store_hidden_messages("session_123", messages)

        # Assert
        mock_dependencies["message_injector"].store_hidden_messages.assert_called_once_with(
            "session_123", messages
        )

    def test_get_session_fingerprint_delegates_to_session_manager(
        self, core_service, mock_dependencies
    ):
        """Test fingerprint calculation delegates correctly."""
        # Arrange
        messages = [Message(role="user", content="Hello")]

        # Act
        result = core_service.get_session_fingerprint(messages)

        # Assert
        assert result == "test_session_id"
        mock_dependencies["session_manager"].calculate_fingerprint.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_diary_context_returns_empty_when_disabled(
        self, core_service
    ):
        """Test diary context injection returns empty when disabled."""
        # Arrange
        messages = [Message(role="user", content="Hello")]

        # Act
        result = await core_service.inject_diary_context(messages)

        # Assert
        assert result == ""


class TestProxyCoreServiceMessageProcessing:
    """Integration tests for full message processing pipeline."""

    @pytest.mark.asyncio
    async def test_process_user_message_full_pipeline(
        self, mock_config, mock_dependencies
    ):
        """Test complete message processing pipeline."""
        # Arrange
        core_service = ProxyCoreService(
            config=mock_config,
            session_manager=mock_dependencies["session_manager"],
            message_injector=mock_dependencies["message_injector"],
            tool_provider=mock_dependencies["tool_provider"],
            context_manager=mock_dependencies["context_manager"],
            thinking_filter=mock_dependencies["thinking_filter"],
            diary_injector=mock_dependencies["diary_injector"],
        )

        mock_openai = Mock()
        mock_openai.chat = AsyncMock(return_value=Mock(
            choices=[{
                "message": {
                    "content": "Test response",
                    "tool_calls": None
                }
            }]
        ))
        mock_openai.close = AsyncMock()

        with patch("src.openai_chat.OpenAIChat", return_value=mock_openai):
            # Act
            result = await core_service.process_user_message(
                user_id="test_user",
                text="Hello, how are you?",
                headers={"X-Papik-Auth": "true"}
            )

        # Assert
        assert result == "Filtered response"

        # Verify pipeline stages
        mock_dependencies["context_manager"].resolve_user_context.assert_called_once()
        mock_dependencies["session_manager"].calculate_fingerprint.assert_called_once()
        mock_dependencies["message_injector"].merge_hidden_context.assert_called_once()
        mock_dependencies["context_manager"].build_system_prompt.assert_called_once()
        mock_openai.chat.assert_called_once()
        mock_dependencies["thinking_filter"].filter_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_user_message_handles_tool_calls(
        self, mock_config, mock_dependencies
    ):
        """Test message processing with tool execution loop."""
        # Arrange
        core_service = ProxyCoreService(
            config=mock_config,
            session_manager=mock_dependencies["session_manager"],
            message_injector=mock_dependencies["message_injector"],
            tool_provider=mock_dependencies["tool_provider"],
            context_manager=mock_dependencies["context_manager"],
            thinking_filter=mock_dependencies["thinking_filter"],
            diary_injector=mock_dependencies["diary_injector"],
        )

        mock_openai = Mock()
        # First call: with tool_calls
        # Second call: final response
        mock_openai.chat = AsyncMock(side_effect=[
            Mock(choices=[{
                "message": {
                    "content": "",
                    "tool_calls": [{"id": "call_1", "function": {"name": "test_tool"}}]
                }
            }]),
            Mock(choices=[{
                "message": {
                    "content": "Final response after tool execution",
                    "tool_calls": None
                }
            }])
        ])
        mock_openai.close = AsyncMock()

        with patch("src.openai_chat.OpenAIChat", return_value=mock_openai):
            # Act
            result = await core_service.process_user_message(
                user_id="test_user",
                text="Execute a tool",
                headers={"X-Papik-Auth": "true"}
            )

        # Assert
        assert result == "Filtered response"
        assert mock_openai.chat.call_count == 2
        mock_dependencies["tool_provider"].execute_tool_calls.assert_called_once()
        mock_dependencies["message_injector"].store_hidden_messages.assert_called()

    @pytest.mark.asyncio
    async def test_process_user_message_error_handling(
        self, mock_config, mock_dependencies
    ):
        """Test error handling in message processing."""
        # Arrange
        core_service = ProxyCoreService(
            config=mock_config,
            session_manager=mock_dependencies["session_manager"],
            message_injector=mock_dependencies["message_injector"],
            tool_provider=mock_dependencies["tool_provider"],
            context_manager=mock_dependencies["context_manager"],
            thinking_filter=mock_dependencies["thinking_filter"],
            diary_injector=mock_dependencies["diary_injector"],
        )

        mock_openai = Mock()
        mock_openai.chat = AsyncMock(side_effect=Exception("LLM error"))
        mock_openai.close = AsyncMock()

        with patch("src.openai_chat.OpenAIChat", return_value=mock_openai):
            # Act
            result = await core_service.process_user_message(
                user_id="test_user",
                text="This will fail",
                headers={"X-Papik-Auth": "true"}
            )

        # Assert
        assert result == "Filtered response"  # Still returns filtered error message
        mock_openai.close.assert_called_once()  # Cleanup happens
