"""Phase 1 – application lifecycle management (startup/shutdown)."""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Coroutine, List

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger("app.lifecycle")

StartupHook = Callable[[], Coroutine]
ShutdownHook = Callable[[], Coroutine]


class Lifecycle:
    """Registers and runs startup/shutdown hooks in order."""

    def __init__(self) -> None:
        self._startup: List[StartupHook] = []
        self._shutdown: List[ShutdownHook] = []

    def on_startup(self, fn: StartupHook) -> StartupHook:
        self._startup.append(fn)
        return fn

    def on_shutdown(self, fn: ShutdownHook) -> ShutdownHook:
        self._shutdown.append(fn)
        return fn

    async def run_startup(self) -> None:
        for fn in self._startup:
            await fn()

    async def run_shutdown(self) -> None:
        for fn in reversed(self._shutdown):
            try:
                await fn()
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.exception("shutdown hook failed: %s", fn)

    @asynccontextmanager
    async def context(self) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        logger.info(
            "lifecycle.startup",
            extra={"event_data": {"event": "lifecycle.startup",
                                  "app_env": settings.app_env}},
        )
        await self.run_startup()
        try:
            yield
        finally:
            await self.run_shutdown()
            logger.info("lifecycle.shutdown")


# Singleton used by main.py
lifecycle = Lifecycle()
