"""Unit tests for WorkerOrchestrator.

Tests worker lifecycle management and orchestration.
Part of ТЗ-001 Phase 1 validation.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.application.worker_orchestrator import WorkerOrchestrator
from src.notification_manager import NotificationManager


class MockWorker:
    """Mock worker for testing."""

    def __init__(self, name: str):
        self.name = name
        self.temporary_context = {}
        self._running = False
        self._run_called = False
        self._wake_up_called = False

    async def run(self):
        """Mock run method."""
        self._running = True
        self._run_called = True
        # Simulate worker running
        try:
            await asyncio.sleep(10)  # Long sleep to simulate work
        except asyncio.CancelledError:
            self._running = False
            raise

    def wake_up(self):
        """Mock wake_up method."""
        self._wake_up_called = True


@pytest.fixture
def notification_manager():
    """Create mock notification manager."""
    return NotificationManager()


@pytest.fixture
def mock_workers():
    """Create mock workers."""
    return [
        MockWorker("worker-0"),
        MockWorker("worker-1"),
        MockWorker("worker-2"),
    ]


@pytest.fixture
def orchestrator(notification_manager, mock_workers):
    """Create WorkerOrchestrator with mocks."""
    return WorkerOrchestrator(
        notification_manager=notification_manager,
        workers=mock_workers
    )


@pytest.mark.asyncio
async def test_orchestrator_start(orchestrator, mock_workers):
    """Test that orchestrator starts all workers."""
    await orchestrator.start()

    # Give workers time to start
    await asyncio.sleep(0.1)

    # Verify all workers started
    for worker in mock_workers:
        assert worker._run_called

    # Verify tasks created
    assert len(orchestrator._tasks) == len(mock_workers)

    # Verify running flag set
    assert orchestrator._running

    # Cleanup
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_start_idempotent(orchestrator, mock_workers):
    """Test that calling start multiple times doesn't create duplicate tasks."""
    await orchestrator.start()
    task_count_1 = len(orchestrator._tasks)

    await orchestrator.start()  # Call again
    task_count_2 = len(orchestrator._tasks)

    # Should still have same number of tasks (no duplicates)
    assert task_count_1 == task_count_2 == len(mock_workers)

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_stop(orchestrator, mock_workers):
    """Test that orchestrator stops all workers cleanly."""
    await orchestrator.start()
    await asyncio.sleep(0.1)  # Let workers start

    # Verify workers are running
    for worker in mock_workers:
        assert worker._run_called

    # Stop orchestrator
    await orchestrator.stop()

    # Verify running flag cleared
    assert not orchestrator._running

    # Verify tasks cleared
    assert len(orchestrator._tasks) == 0

    # Verify all workers' context cleared
    for worker in mock_workers:
        assert len(worker.temporary_context) == 0


@pytest.mark.asyncio
async def test_orchestrator_stop_idempotent(orchestrator):
    """Test that calling stop multiple times is safe."""
    await orchestrator.start()
    await orchestrator.stop()

    # Call stop again - should not raise
    await orchestrator.stop()

    assert not orchestrator._running


@pytest.mark.asyncio
async def test_orchestrator_wake_up_all(orchestrator, mock_workers):
    """Test that wake_up_all wakes all workers."""
    await orchestrator.start()
    await asyncio.sleep(0.1)

    # Wake up all workers
    orchestrator.wake_up_all()

    # Verify all workers were woken up
    for worker in mock_workers:
        assert worker._wake_up_called

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_workers_property(orchestrator, mock_workers):
    """Test that workers property exposes worker list."""
    workers = orchestrator.workers

    assert len(workers) == len(mock_workers)
    assert workers is mock_workers


@pytest.mark.asyncio
async def test_orchestrator_task_naming(orchestrator, mock_workers):
    """Test that tasks are named appropriately."""
    await orchestrator.start()
    await asyncio.sleep(0.1)

    # Verify task names
    task_names = [task.get_name() for task in orchestrator._tasks]

    expected_names = [f"worker-{worker.name}" for worker in mock_workers]
    assert set(task_names) == set(expected_names)

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_handles_worker_exception(notification_manager):
    """Test that orchestrator handles worker exceptions gracefully."""

    class FailingWorker:
        def __init__(self, name: str):
            self.name = name
            self.temporary_context = {}

        async def run(self):
            raise RuntimeError("Worker failed")

        def wake_up(self):
            pass

    workers = [FailingWorker("failing-worker")]
    orchestrator = WorkerOrchestrator(
        notification_manager=notification_manager,
        workers=workers
    )

    await orchestrator.start()
    await asyncio.sleep(0.1)

    # Stop should still work despite exception
    await orchestrator.stop()

    assert not orchestrator._running


@pytest.mark.asyncio
async def test_orchestrator_cancellation(orchestrator, mock_workers):
    """Test that orchestrator cancels tasks properly."""
    await orchestrator.start()
    await asyncio.sleep(0.1)

    # Tasks should be running
    running_tasks = [t for t in orchestrator._tasks if not t.done()]
    assert len(running_tasks) > 0

    # Stop should cancel all tasks
    await orchestrator.stop()

    # All tasks should be done (cancelled)
    for task in orchestrator._tasks:
        assert task.done()


@pytest.mark.asyncio
async def test_orchestrator_context_cleanup(orchestrator, mock_workers):
    """Test that worker context is cleared on stop."""
    # Add some context to workers
    for i, worker in enumerate(mock_workers):
        worker.temporary_context[i] = [f"message-{i}"]

    await orchestrator.start()
    await asyncio.sleep(0.1)
    await orchestrator.stop()

    # Verify context cleared
    for worker in mock_workers:
        assert len(worker.temporary_context) == 0


@pytest.mark.asyncio
async def test_orchestrator_with_zero_workers(notification_manager):
    """Test orchestrator with no workers."""
    orchestrator = WorkerOrchestrator(
        notification_manager=notification_manager,
        workers=[]
    )

    await orchestrator.start()
    assert orchestrator._running
    assert len(orchestrator._tasks) == 0

    await orchestrator.stop()
    assert not orchestrator._running


@pytest.mark.asyncio
async def test_orchestrator_lifecycle_integration(notification_manager):
    """Test full lifecycle: start → wake_up_all → stop."""
    workers = [MockWorker(f"worker-{i}") for i in range(3)]
    orchestrator = WorkerOrchestrator(
        notification_manager=notification_manager,
        workers=workers
    )

    # Start
    await orchestrator.start()
    assert orchestrator._running
    await asyncio.sleep(0.1)

    # Verify started
    for worker in workers:
        assert worker._run_called

    # Wake up all
    orchestrator.wake_up_all()
    for worker in workers:
        assert worker._wake_up_called

    # Stop
    await orchestrator.stop()
    assert not orchestrator._running

    # Verify cleanup
    assert len(orchestrator._tasks) == 0
    for worker in workers:
        assert len(worker.temporary_context) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
