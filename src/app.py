"""Refactored application composition root.

This replaces the 728-line app.py god object with a clean composition root
following ТЗ-001 punkt 5 (clean architecture).

Responsibilities:
- Wire up dependencies via DI container
- Delegate to focused service classes
- Minimal orchestration logic (<100 lines)
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from .application.lifecycle import ApplicationLifecycle
from .application.proactive_service import ProactiveMessageService
from .application.sleep_scheduler import SleepScheduler
from .application.telegram_handler import TelegramEventHandler
from .application.worker_orchestrator import WorkerOrchestrator
from .config import Config, load_config
from .di.container import create_dependencies

logger = logging.getLogger(__name__)


class App:
    """Kunipy application composition root.

    Wires together all components via dependency injection and delegates
    to focused service classes. Follows clean architecture pattern from
    C++ kuni port specification (ТЗ-001).
    """

    def __init__(self, config: Config, working_dir: str = "data"):
        """Initialize application.

        Args:
            config: Application configuration
            working_dir: Directory for persistent data
        """
        self._config = config
        self._working_dir = Path(working_dir)
        self._working_dir.mkdir(parents=True, exist_ok=True)

        # DI container (created during initialize)
        self._deps: Optional = None

        # Service orchestrators
        self._lifecycle: ApplicationLifecycle | None = None
        self._telegram_handler: TelegramEventHandler | None = None
        self._worker_orchestrator: WorkerOrchestrator | None = None
        self._proactive_service: ProactiveMessageService | None = None
        self._sleep_scheduler: SleepScheduler | None = None

    async def initialize(self) -> None:
        """Initialize all components via dependency injection."""
        logger.info("Initializing application components...")

        # Create DI container with all dependencies
        self._deps = await create_dependencies(self._working_dir, self._config)

        # Initialize service orchestrators
        self._lifecycle = ApplicationLifecycle(self._deps, self._working_dir)
        self._telegram_handler = TelegramEventHandler(self._deps)
        self._sleep_scheduler = SleepScheduler(
            deps=self._deps,
            night_hour=4  # 4 AM consolidation
        )
        self._proactive_service = ProactiveMessageService(self._deps)

        # Create worker orchestrator
        from .worker import Worker
        workers = [
            Worker(
                name=f"worker-{i}",
                openai=self._deps.openai_chat,
                notification_manager=self._deps.notification_manager,
                telegram=self._deps.telegram_client,
                diary=self._deps.diary,
                config=self._deps.config,
            )
            for i in range(self._deps.config.worker_count)
        ]
        self._worker_orchestrator = WorkerOrchestrator(
            notification_manager=self._deps.notification_manager,
            workers=workers
        )

        logger.info("All components initialized")

    async def start(self) -> None:
        """Start the application and all background services."""
        if not self._deps:
            raise RuntimeError("App not initialized - call initialize() first")

        # Start lifecycle
        await self._lifecycle.start()

        # Start workers
        await self._worker_orchestrator.start()

        # Set up Telegram event handler if enabled
        if self._deps.config.telegram_enabled and self._deps.telegram_client:
            # Register event callback
            self._deps.telegram_client.add_event_handler(
                self._telegram_handler.handle_event
            )
            # Send startup notifications
            await self._telegram_handler.send_startup_notifications()

        # Start proactive messaging if Telegram enabled
        if self._deps.config.telegram_enabled and self._deps.telegram_client:
            task = self._proactive_service.start()
            if task:
                self._lifecycle.add_background_task(task, "proactive-service")

        # Start sleep consolidation if diary enabled
        if self._deps.diary:
            task = self._sleep_scheduler.start()
            if task:
                self._lifecycle.add_background_task(task, "sleep-scheduler")

        # Start proxy server if enabled
        if self._deps.config.proxy_enabled:
            logger.info(f"Proxy enabled, starting server on port {self._deps.config.proxy_port}")
            await self._start_proxy_server()

        # Start metrics server if enabled
        if self._deps.config.metrics_enabled:
            await self._start_metrics_server()

        logger.info("Kunipy is running")

        # Wait for shutdown signal
        await self._lifecycle.wait_for_shutdown()

    async def stop(self) -> None:
        """Stop the application gracefully."""
        logger.info("Stopping application...")

        # Dump remaining worker context to diary
        if self._deps.diary and self._worker_orchestrator:
            await self._dump_worker_context()

        # Stop workers
        if self._worker_orchestrator:
            await self._worker_orchestrator.stop()

        # Stop lifecycle
        if self._lifecycle:
            await self._lifecycle.stop()

        logger.info("Application stopped")

    async def _start_proxy_server(self) -> None:
        """Start OpenAI-compatible proxy server."""
        import uvicorn

        from .proxy_server import create_proxy_app

        app = create_proxy_app(self._deps.diary)
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self._deps.config.proxy_port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve(), name="proxy-server")
        self._lifecycle.add_background_task(task, "proxy-server")
        logger.info(f"Proxy server started on port {self._deps.config.proxy_port}")

    async def _start_metrics_server(self) -> None:
        """Start Prometheus metrics endpoint."""
        from .metrics import start_metrics_server

        task = asyncio.create_task(
            start_metrics_server(self._deps.config.metrics_port),
            name="metrics-server"
        )
        self._lifecycle.add_background_task(task, "metrics-server")
        logger.info(f"Metrics server started on port {self._deps.config.metrics_port}")

    async def _dump_worker_context(self) -> None:
        """Dump remaining worker context to diary before shutdown."""
        if not self._worker_orchestrator:
            return

        from datetime import datetime

        for worker in self._worker_orchestrator.workers:
            for chat_id, messages in worker.temporary_context.items():
                if not messages:
                    continue

                # Build summary
                summary = f"Conversation dump at {datetime.now(self._config.timezone_info).isoformat()}\n"
                for msg in messages:
                    if hasattr(msg, "role") and hasattr(msg, "content"):
                        summary += f"{msg.role}: {msg.content[:200]}\n"

                await self._deps.diary.add_entry(summary, confidence=0.3)
                logger.debug(f"Dumped {len(messages)} messages from chat {chat_id}")


async def main() -> None:
    """Application entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load config (no singleton - clean DI)
    try:
        config = load_config("config.toml")
    except FileNotFoundError:
        logger.error("config.toml not found")
        sys.exit(1)

    # Create and run app with explicit config
    app = App(config=config, working_dir="data")
    try:
        await app.initialize()
        await app.start()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
