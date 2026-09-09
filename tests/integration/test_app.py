"""Integration tests for app.

Tests full application lifecycle and component integration.
Part of ТЗ-001 Phase 1 validation.
"""

import asyncio
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, AsyncMock, patch

from src.app import App
from src.config import Config, Endpoint, EndpointAndModel, LockdownMode


@pytest.fixture
def minimal_config():
    """Create minimal test configuration."""
    config = Config()

    # Minimal LLM config
    config.llm = EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="test-model"
    )

    config.embedding = EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="test-embedding"
    )

    # Disable optional features
    config.telegram_enabled = False
    config.diary_enabled = False
    config.proxy_enabled = False
    config.metrics_enabled = False

    config.worker_count = 1
    config.lockdown = LockdownMode.NONE

    return config


@pytest.mark.asyncio
async def test_app_initialization(minimal_config):
    """Test that app initializes without errors."""
    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)

        # Verify initial state
        assert app._config is minimal_config
        assert app._working_dir == Path(tmpdir)
        assert app._deps is None  # Not initialized yet

        # Initialize
        await app.initialize()

        # Verify components created
        assert app._deps is not None
        assert app._lifecycle is not None
        assert app._telegram_handler is not None
        assert app._worker_orchestrator is not None
        assert app._sleep_scheduler is not None


@pytest.mark.asyncio
async def test_app_start_stop_lifecycle(minimal_config):
    """Test full app start/stop lifecycle."""
    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)

        await app.initialize()

        # Start app in background
        start_task = asyncio.create_task(app.start())

        # Give it time to start
        await asyncio.sleep(0.2)

        # Verify components started
        assert app._lifecycle._running

        # Stop app
        await app.stop()

        # Verify stopped
        assert not app._lifecycle._running

        # Wait for start task to complete
        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except asyncio.TimeoutError:
            start_task.cancel()


@pytest.mark.asyncio
async def test_app_creates_working_directory(minimal_config):
    """Test that app creates working directory if it doesn't exist."""
    with TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir) / "new_dir" / "data"

        # Directory doesn't exist yet
        assert not working_dir.exists()

        app = App(config=minimal_config, working_dir=str(working_dir))

        # After initialization, directory should exist
        assert working_dir.exists()


@pytest.mark.asyncio
async def test_app_with_telegram_disabled(minimal_config):
    """Test app runs correctly with Telegram disabled."""
    minimal_config.telegram_enabled = False

    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        # Verify Telegram components are None
        assert app._deps.telegram_client is None

        # App should still start
        start_task = asyncio.create_task(app.start())
        await asyncio.sleep(0.2)

        await app.stop()

        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except asyncio.TimeoutError:
            start_task.cancel()


@pytest.mark.asyncio
async def test_app_with_diary_enabled(minimal_config):
    """Test app with diary enabled."""
    minimal_config.diary_enabled = True

    with TemporaryDirectory() as tmpdir:
        minimal_config.diary_dir = str(Path(tmpdir) / "diary")

        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        # Verify diary created
        assert app._deps.diary is not None

        # Verify diary directory created
        assert Path(minimal_config.diary_dir).exists()


@pytest.mark.asyncio
async def test_app_worker_orchestrator_integration(minimal_config):
    """Test that workers are properly orchestrated."""
    minimal_config.worker_count = 2

    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        # Verify workers created
        assert app._worker_orchestrator is not None
        assert len(app._worker_orchestrator.workers) == 2

        # Start and verify workers start
        start_task = asyncio.create_task(app.start())
        await asyncio.sleep(0.2)

        # Workers should be running
        assert app._worker_orchestrator._running

        await app.stop()

        # Workers should be stopped
        assert not app._worker_orchestrator._running

        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except asyncio.TimeoutError:
            start_task.cancel()


@pytest.mark.asyncio
async def test_app_stop_idempotent(minimal_config):
    """Test that calling stop multiple times is safe."""
    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        start_task = asyncio.create_task(app.start())
        await asyncio.sleep(0.2)

        # First stop
        await app.stop()

        # Second stop - should not raise
        await app.stop()

        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except asyncio.TimeoutError:
            start_task.cancel()


@pytest.mark.asyncio
async def test_app_initialize_before_start(minimal_config):
    """Test that start fails gracefully if initialize not called."""
    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)

        # Try to start without initializing
        with pytest.raises(RuntimeError, match="not initialized"):
            await app.start()


@pytest.mark.asyncio
async def test_app_sleep_scheduler_integration(minimal_config):
    """Test sleep scheduler integration with diary."""
    minimal_config.diary_enabled = True

    with TemporaryDirectory() as tmpdir:
        minimal_config.diary_dir = str(Path(tmpdir) / "diary")

        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        # Verify sleep scheduler created
        assert app._sleep_scheduler is not None

        # Start app
        start_task = asyncio.create_task(app.start())
        await asyncio.sleep(0.2)

        # Sleep scheduler should have background task registered
        # (though it won't actually run consolidation in short test)

        await app.stop()

        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except asyncio.TimeoutError:
            start_task.cancel()


@pytest.mark.asyncio
async def test_app_context_dumping_on_shutdown(minimal_config):
    """Test that worker context is dumped to diary on shutdown."""
    minimal_config.diary_enabled = True
    minimal_config.worker_count = 1

    with TemporaryDirectory() as tmpdir:
        minimal_config.diary_dir = str(Path(tmpdir) / "diary")

        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        # Add some mock context to worker
        from src.openai_chat import Message
        worker = app._worker_orchestrator.workers[0]
        worker.temporary_context[123] = [
            Message(role="user", content="test message")
        ]

        start_task = asyncio.create_task(app.start())
        await asyncio.sleep(0.2)

        # Stop should dump context
        await app.stop()

        # Verify context was cleared
        assert len(worker.temporary_context) == 0

        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except asyncio.TimeoutError:
            start_task.cancel()


@pytest.mark.asyncio
async def test_app_config_isolation(minimal_config):
    """Test that each app instance has isolated config."""
    with TemporaryDirectory() as tmpdir1, TemporaryDirectory() as tmpdir2:
        config1 = minimal_config
        config1.worker_count = 1

        config2 = Config()
        config2.llm = minimal_config.llm
        config2.embedding = minimal_config.embedding
        config2.telegram_enabled = False
        config2.diary_enabled = False
        config2.worker_count = 2

        app1 = App(config=config1, working_dir=tmpdir1)
        app2 = App(config=config2, working_dir=tmpdir2)

        await app1.initialize()
        await app2.initialize()

        # Verify configs are isolated
        assert app1._config.worker_count == 1
        assert app2._config.worker_count == 2

        # Verify different worker counts
        assert len(app1._worker_orchestrator.workers) == 1
        assert len(app2._worker_orchestrator.workers) == 2


@pytest.mark.asyncio
async def test_app_delivery_storage_initialized(minimal_config):
    """Test that delivery storage is initialized."""
    with TemporaryDirectory() as tmpdir:
        app = App(config=minimal_config, working_dir=tmpdir)
        await app.initialize()

        # Verify delivery database exists
        db_path = Path(tmpdir) / "delivery.db"
        assert db_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
