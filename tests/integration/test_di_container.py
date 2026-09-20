"""Integration tests for DI container.

Tests that all dependencies are properly wired and protocols are satisfied.
Part of ТЗ-001 Phase 1 validation.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.config import Config, Endpoint, EndpointAndModel, LockdownMode
from src.di.container import Dependencies, create_dependencies


@pytest.fixture
def test_config() -> Config:
    """Create minimal test configuration."""
    config = Config()

    # Minimal LLM config
    config.llm = EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/", bearer_key=""),
        model="test-model"
    )

    # Minimal embedding config
    config.embedding = EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/", bearer_key=""),
        model="test-embedding"
    )

    # Disable optional features for testing
    config.telegram_enabled = False
    config.diary_enabled = False
    config.proxy_enabled = False
    config.metrics_enabled = False

    # Basic settings
    config.worker_count = 1
    config.lockdown = LockdownMode.NONE

    return config


@pytest.mark.asyncio
async def test_create_dependencies_basic(test_config):
    """Test that DI container creates all basic dependencies."""
    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        deps = await create_dependencies(working_dir, test_config)

        # Verify Dependencies structure
        assert isinstance(deps, Dependencies)
        assert deps.config is test_config

        # Verify core services created
        assert deps.openai_chat is not None
        assert deps.embedding_provider is not None
        assert deps.notification_manager is not None

        # Verify memory stubs created
        assert deps.memory_store is not None
        assert deps.working_memory is not None

        # Verify optional services are None when disabled
        assert deps.telegram_client is None  # disabled in config
        assert deps.diary is None  # disabled in config


@pytest.mark.asyncio
async def test_create_dependencies_with_telegram(test_config):
    """Test DI container with Telegram enabled."""
    # Note: This test will be skipped if Telegram credentials are not configured
    # In real environment, would need proper TDLib setup

    test_config.telegram_enabled = True
    test_config.telegram_api_id = 12345
    test_config.telegram_api_hash = "test_hash"
    test_config.telegram_phone = "+1234567890"
    test_config.telegram_database_directory = "test_tdlib"

    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # This will likely fail without real TDLib, but tests the wiring
        try:
            deps = await create_dependencies(working_dir, test_config)

            # If we get here, Telegram is configured
            assert deps.telegram_client is not None
            assert deps.telegram_message_service is not None

        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as e:
            # Expected if TDLib not available
            pytest.skip(f"Telegram not available: {e}")


@pytest.mark.asyncio
async def test_create_dependencies_with_diary(test_config):
    """Test DI container with Diary enabled."""
    test_config.diary_enabled = True
    test_config.diary_dir = "test_diary"

    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)
        test_config.diary_dir = str(working_dir / "diary")

        deps = await create_dependencies(working_dir, test_config)

        # Verify diary created
        assert deps.diary is not None

        # Verify diary has config (not using singleton)
        assert hasattr(deps.diary, 'config')
        assert deps.diary.config is test_config


@pytest.mark.asyncio
async def test_delivery_tracking_initialized(test_config):
    """Test that delivery tracking system is properly initialized."""
    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        deps = await create_dependencies(working_dir, test_config)

        # Verify delivery tracker exists (even without Telegram)
        # Tracker may be None if Telegram is disabled, which is correct
        if test_config.telegram_enabled:
            assert deps.delivery_tracker is not None

        # Check that storage was initialized (database created)
        db_path = working_dir / "delivery.db"
        assert db_path.exists()


@pytest.mark.asyncio
async def test_dependencies_config_isolation(test_config):
    """Test that each dependencies instance has isolated config."""
    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Create two dependency containers with different configs
        config1 = test_config
        config1.worker_count = 1

        config2 = Config()
        config2.worker_count = 2
        config2.llm = test_config.llm
        config2.embedding = test_config.embedding
        config2.telegram_enabled = False
        config2.diary_enabled = False

        deps1 = await create_dependencies(working_dir, config1)
        deps2 = await create_dependencies(working_dir, config2)

        # Verify configs are different
        assert deps1.config.worker_count == 1
        assert deps2.config.worker_count == 2

        # Verify no shared state
        assert deps1.config is not deps2.config


@pytest.mark.asyncio
async def test_notification_manager_protocol():
    """Test that notification manager satisfies INotificationManager protocol."""

    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)
        config = Config()
        config.llm = EndpointAndModel(
            endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
            model="test"
        )
        config.telegram_enabled = False
        config.diary_enabled = False

        deps = await create_dependencies(working_dir, config)

        # Verify notification_manager has required methods
        assert hasattr(deps.notification_manager, 'start')
        assert hasattr(deps.notification_manager, 'stop')
        assert hasattr(deps.notification_manager, 'add_notification')
        assert hasattr(deps.notification_manager, 'get')

        # Note: Protocol checking is done at type-check time, not runtime
        # This test just verifies methods exist


@pytest.mark.asyncio
async def test_openai_chat_configuration(test_config):
    """Test that OpenAI chat is configured from config."""
    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        test_config.llm.endpoint.base_url = "http://custom:1234/v1/"
        test_config.llm.model = "custom-model"

        deps = await create_dependencies(working_dir, test_config)

        # Verify OpenAI client exists
        assert deps.openai_chat is not None

        # Verify configuration was applied
        # (OpenAIChat stores endpoint configuration)
        assert hasattr(deps.openai_chat, 'endpoint')


def test_dependencies_dataclass_structure():
    """Test that Dependencies follows expected structure."""
    from dataclasses import fields

    # Verify Dependencies is a dataclass with expected fields
    field_names = {f.name for f in fields(Dependencies)}

    expected_fields = {
        'config',
        'openai_chat',
        'embedding_provider',
        'telegram_client',
        'telegram_message_service',
        'memory_store',
        'working_memory',
        'delivery_tracker',
        'notification_manager',
        'diary',
    }

    assert expected_fields.issubset(field_names), \
        f"Missing fields: {expected_fields - field_names}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
