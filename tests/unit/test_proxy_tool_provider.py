"""Unit tests for proxy tool provider."""

import pytest

from src.application.proxy.tool_provider import ProxyToolProvider
from src.config import Config
from src.openai_chat import Message, OpenAIChat


@pytest.fixture
def config():
    """Create test config."""
    cfg = Config()
    cfg.capability_web_search = True
    cfg.diary_enabled = True
    return cfg


@pytest.fixture
def openai_client():
    """Create OpenAI client."""
    return OpenAIChat()


def test_tool_provider_initialization(config, openai_client):
    """Test tool provider initialization."""
    provider = ProxyToolProvider(config, diary=None, openai=openai_client)
    assert provider is not None


def test_tool_provider_no_tools(openai_client):
    """Test provider with no tools enabled."""
    config = Config()
    config.capability_web_search = False
    config.diary_enabled = False

    provider = ProxyToolProvider(config, diary=None, openai=openai_client)

    tools = provider.get_tool_definitions()
    assert len(tools) == 0


def test_tool_provider_with_web_search(openai_client):
    """Test provider with web search enabled."""
    config = Config()
    config.capability_web_search = True
    config.diary_enabled = False

    provider = ProxyToolProvider(config, diary=None, openai=openai_client)

    tools = provider.get_tool_definitions()
    tool_names = [t.function["name"] for t in tools if t.function]

    assert "web_search" in tool_names


def test_tool_provider_with_diary(config, openai_client):
    """Test provider with diary enabled."""
    from src.diary import Diary

    diary = Diary()
    provider = ProxyToolProvider(config, diary=diary, openai=openai_client)

    tools = provider.get_tool_definitions()
    tool_names = [t.function["name"] for t in tools if t.function]

    assert "ask" in tool_names


def test_get_tool_schemas(config, openai_client):
    """Test getting tool schemas in OpenAI format."""
    provider = ProxyToolProvider(config, diary=None, openai=openai_client)

    schemas = provider.get_tool_schemas()

    # Should have web_search
    assert schemas is not None
    assert len(schemas) > 0
    assert all("type" in schema for schema in schemas)
    assert all("function" in schema for schema in schemas)


def test_get_tool_schemas_no_tools(openai_client):
    """Test schemas with no tools."""
    config = Config()
    config.capability_web_search = False

    provider = ProxyToolProvider(config, diary=None, openai=openai_client)

    schemas = provider.get_tool_schemas()
    assert schemas is None


def test_tool_count(config, openai_client):
    """Test tool count."""
    provider = ProxyToolProvider(config, diary=None, openai=openai_client)

    count = provider.get_tool_count()
    assert count > 0  # At least web_search


@pytest.mark.asyncio
async def test_execute_tool_calls_empty(config, openai_client):
    """Test executing empty tool calls."""
    provider = ProxyToolProvider(config, diary=None, openai=openai_client)

    messages = [Message(role="user", content="Test")]
    results = await provider.execute_tool_calls([], messages)

    assert len(results) == 0


def test_proxy_tools_exclude_telegram(config, openai_client):
    """Test that Telegram tools are not available in proxy."""
    from src.diary import Diary

    diary = Diary()
    provider = ProxyToolProvider(config, diary=diary, openai=openai_client)

    tools = provider.get_tool_definitions()
    tool_names = [t.function["name"] for t in tools if t.function]

    # Telegram tools should NOT be in proxy
    assert "send_message" not in tool_names
    assert "get_chats" not in tool_names
    assert "edit_message" not in tool_names


def test_proxy_tools_exclude_admin(config, openai_client):
    """Test that admin tools are not available in proxy."""
    from src.diary import Diary

    diary = Diary()
    provider = ProxyToolProvider(config, diary=diary, openai=openai_client)

    tools = provider.get_tool_definitions()
    tool_names = [t.function["name"] for t in tools if t.function]

    # Admin tools should NOT be in proxy
    assert "ban_user" not in tool_names
    assert "set_user_tag" not in tool_names
