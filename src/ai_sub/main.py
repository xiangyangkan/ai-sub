"""Entry point for the AI Release Notification Service."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from ai_sub.config import settings
from ai_sub.notifier.telegram_topics import ensure_topics
from ai_sub.scheduler import (
    create_scheduler,
    fetch_and_notify,
    fetch_and_notify_blogs,
    fetch_and_notify_sitemap,
)
from ai_sub.fetcher.sitemap import load_sitemap_sources


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def _run() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting AI Release Notification Service")

    await ensure_topics()

    scheduler = create_scheduler()
    scheduler.start()

    # Run first fetch immediately
    if settings.release_enabled:
        logger.info("Running initial release fetch...")
        try:
            await fetch_and_notify()
        except Exception as e:
            logger.error("Initial release fetch failed: %s", e)

    if settings.blog_enabled:
        logger.info("Running initial blog fetch...")
        try:
            await fetch_and_notify_blogs()
        except Exception as e:
            logger.error("Initial blog fetch failed: %s", e)

    if settings.sitemap_enabled:
        logger.info("Running initial sitemap fetch...")
        for source in load_sitemap_sources(settings.sitemap_config_path):
            try:
                await fetch_and_notify_sitemap(source)
            except Exception as e:
                logger.error("Initial sitemap fetch failed for %s: %s", source.name, e)

    # Wait for shutdown signal
    stop = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop.wait()
    scheduler.shutdown(wait=False)
    logger.info("Shutdown complete")


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
