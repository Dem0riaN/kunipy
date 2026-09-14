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
from typing import TYPE_CHECKING, Optional

from .application.lifecycle import ApplicationLifecycle
from .application.proactive_service import ProactiveMessageService
from .application.sleep_scheduler import SleepScheduler
from .application.telegram_handler import TelegramEventHandler
from .application.worker_orchestrator import WorkerOrchestrator
from .config import Config, load_config
from .di.container import create_dependencies

if TYPE_CHECKING:
    from .desktop import DesktopCharacter

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

        # Desktop character (ТЗ-004)
        self._desktop: DesktopCharacter | None = None

        # Proxy server handle (for graceful shutdown)
        self._proxy_server = None

        # Shutdown coordination (Phase 0: graceful shutdown fix)
        self._shutdown_event = asyncio.Event()
        self._stopped = False  # idempotency guard for App.stop()

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
        from .memory_integrated_worker import MemoryIntegratedWorker
        from .worker import Worker

        # Choose worker type based on memory system availability
        if self._deps.memory_service and self._deps.memory_formation:
            # Use memory-integrated worker
            workers = [
                MemoryIntegratedWorker(
                    name=f"worker-{i}",
                    openai=self._deps.openai_chat,
                    notification_manager=self._deps.notification_manager,
                    telegram=self._deps.telegram_client,
                    diary=self._deps.diary,
                    config=self._deps.config,
                    memory_service=self._deps.memory_service,
                    memory_formation=self._deps.memory_formation,
                    diary_dump_service=self._deps.diary_dump_service,
                    diary_context_injector=self._deps.diary_context_injector,  # Phase 4
                )
                for i in range(self._deps.config.worker_count)
            ]
            logger.info("Using MemoryIntegratedWorker with automatic memory formation")
        else:
            # Fallback to basic worker
            workers = [
                Worker(
                    name=f"worker-{i}",
                    openai=self._deps.openai_chat,
                    notification_manager=self._deps.notification_manager,
                    telegram=self._deps.telegram_client,
                    diary=self._deps.diary,
                    config=self._deps.config,
                    memory_service=self._deps.memory_service,  # ТЗ-002
                    diary_dump_service=self._deps.diary_dump_service,  # Phase 3
                    diary_context_injector=self._deps.diary_context_injector,  # Phase 4
                )
                for i in range(self._deps.config.worker_count)
            ]
            logger.info("Using basic Worker (memory system not fully configured)")

        self._worker_orchestrator = WorkerOrchestrator(
            notification_manager=self._deps.notification_manager,
            workers=workers
        )

        logger.info("All components initialized")

    async def start(self) -> None:
        """Start the application and all background services."""
        if not self._deps:
            raise RuntimeError("App not initialized - call initialize() first")

        self._shutdown_event = asyncio.Event()
        self._stopped = False

        # try/finally covers the WHOLE startup too: a Ctrl+C during startup
        # (CancelledError injected at any await) must still reach App.stop()
        # so started components are torn down.
        try:
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

            # Stdin shutdown listener (only in interactive terminal)
            if sys.stdin and sys.stdin.isatty():
                stdin_task = asyncio.create_task(
                    self._stdin_command_listener(), name="stdin-listener"
                )
                self._lifecycle.add_background_task(stdin_task, "stdin-listener")

            # Start desktop character (ТЗ-004) — AFTER workers started
            if self._deps.config.desktop_enabled:
                try:
                    from .desktop import DesktopCharacter
                    from .desktop.config import DesktopConfig

                    self._desktop = DesktopCharacter(
                        DesktopConfig.from_app_config(self._deps.config)
                    )
                    await self._desktop.start()
                    logger.info("Desktop character started")
                except ImportError:
                    logger.warning("Desktop dependencies not installed, skipping")
                except Exception:
                    logger.exception("Desktop startup failed, continuing without desktop")

            logger.info("Kunipy is running")

            # Wait for shutdown signal.
            # lifecycle.stop() is idempotent (guard in ApplicationLifecycle.stop()),
            # so the double call (lifecycle's finally + App.stop()) is safe.
            await self._lifecycle.wait_for_shutdown(self._shutdown_event)
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the application gracefully.

        Idempotent: safe to call multiple times (e.g. both from stdin listener
        signal path and from wait_for_shutdown finally). Only the first call
        performs the actual shutdown sequence.
        """
        if self._stopped:
            return
        self._stopped = True

        # Unblock wait_for_shutdown if it is still waiting (e.g. stop() called
        # from outside the start() flow); harmless when start() already finished.
        self._shutdown_event.set()

        logger.info("Stopping application...")

        # Stop desktop character (ТЗ-004)
        if self._desktop:
            try:
                await self._desktop.stop()
            except Exception:
                logger.exception("Desktop shutdown failed (ignored)")

        # Dump remaining worker context to diary
        if self._deps.diary and self._worker_orchestrator:
            await self._dump_worker_context()

        # Signal proxy server to exit gracefully BEFORE lifecycle cancels tasks.
        # uvicorn's Server.should_exit triggers a clean shutdown of the starlette
        # lifespan, avoiding CancelledError from _GatheringFuture.
        if self._proxy_server is not None:
            self._proxy_server.should_exit = True
            # Wait for uvicorn to finish its lifespan cleanup (up to 2s)
            if self._lifecycle:
                for task in self._lifecycle._tasks:
                    if task.get_name() == "proxy-server":
                        try:
                            await asyncio.wait_for(task, timeout=2.0)
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            pass
                        break

        # Stop workers
        if self._worker_orchestrator:
            await self._worker_orchestrator.stop()

        # Stop lifecycle (idempotent — guard in ApplicationLifecycle.stop())
        if self._lifecycle:
            await self._lifecycle.stop()

        logger.info("Application stopped")

    async def _stdin_command_listener(self) -> None:
        """Read commands from stdin in an interactive terminal.

        Only signals the shutdown event — does not call stop() directly.
        The actual shutdown is handled by start()'s finally block.

        Uses a daemon reader thread + polling instead of run_in_executor:
        a default-executor thread blocked on readline() would hang
        asyncio.run()'s executor shutdown at exit.
        """
        import queue
        import threading

        lines: queue.Queue[str] = queue.Queue()

        def reader() -> None:
            while True:
                line = sys.stdin.readline()
                lines.put(line)
                if not line:  # EOF
                    return

        threading.Thread(target=reader, daemon=True, name="stdin-reader").start()

        while self._lifecycle and self._lifecycle.is_running():
            try:
                line = lines.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.2)
                continue

            if not line:
                break  # EOF
            command = line.strip().lower()
            if command == "shutdown":
                logger.info("Shutdown command received from stdin")
                self._shutdown_event.set()
                break

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
        self._proxy_server = server
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
        """Dump remaining worker context to diary before shutdown.

        Phase 3: Uses DiaryDumpService.dump_on_shutdown() for LLM-summarized
        entries when available. Falls back to raw dump otherwise.

        Defensively hardened:
        - Snapshots dict to avoid RuntimeError if worker mutates during dump
        - Per-chat try/except so one embedding failure doesn't abort the rest
        - Extracts text from multimodal content (list[dict]) before truncating
        """
        if not self._worker_orchestrator:
            return

        # Phase 3: LLM-summarized dump via DiaryDumpService
        if self._deps.diary_dump_service:
            all_chats: dict[int, list] = {}
            for worker in self._worker_orchestrator.workers:
                # Snapshot: worker tasks may still be alive and mutating the dict
                for chat_id, messages in list(worker.temporary_context.items()):
                    if messages:
                        all_chats[chat_id] = messages
            if all_chats:
                try:
                    count = await self._deps.diary_dump_service.dump_on_shutdown(all_chats)
                    logger.info(f"Shutdown dump: {count} diary entries created")
                except Exception:
                    logger.exception("DiaryDumpService dump failed, falling back to raw dump")
                    await self._raw_dump_fallback()
            return

        # Fallback: raw dump (when diary_dump_service not configured)
        await self._raw_dump_fallback()

    async def _raw_dump_fallback(self) -> None:
        """Raw dump fallback when DiaryDumpService is not available.

        Writes truncated message summaries directly to diary with low confidence.
        """
        if not self._worker_orchestrator or not self._deps.diary:
            return

        from datetime import datetime

        for worker in self._worker_orchestrator.workers:
            # Snapshot: worker tasks may still be alive and mutating the dict
            for chat_id, messages in list(worker.temporary_context.items()):
                if not messages:
                    continue

                # Build summary
                summary = f"Conversation dump at {datetime.now(self._config.timezone_info).isoformat()}\n"
                for msg in messages:
                    if hasattr(msg, "role") and hasattr(msg, "content"):
                        # Extract text from multimodal content (list[dict] with base64)
                        content = msg.content
                        if isinstance(content, list):
                            text_parts = [
                                p.get("text", "") for p in content
                                if isinstance(p, dict) and p.get("type") == "text"
                            ]
                            content = " ".join(text_parts)
                        summary += f"{msg.role}: {content[:200]}\n"

                try:
                    await self._deps.diary.add_entry(summary, confidence=0.3)
                    logger.debug(f"Dumped {len(messages)} messages from chat {chat_id}")
                except Exception:
                    logger.exception(f"Failed to dump context for chat {chat_id}")


async def main() -> None:
    """Application entry point."""
    import os
    import platform

    # Add data directory to DLL search path on Windows
    if platform.system().lower() == "windows":
        data_dir = os.path.abspath("data")
        if os.path.exists(data_dir):
            os.add_dll_directory(data_dir)
            # Also add to PATH for ctypes.util.find_library()
            os.environ["PATH"] = f"{data_dir}{os.pathsep}{os.environ.get('PATH', '')}"

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
    except asyncio.CancelledError:
        # Ctrl+C during startup: App.start()'s finally already ran App.stop().
        # A re-injected cancellation may surface here; that is still a clean
        # interrupt, not a fatal error.
        logger.info("Interrupted")
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
