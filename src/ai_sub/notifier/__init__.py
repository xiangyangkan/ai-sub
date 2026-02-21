import asyncio
import logging

from ai_sub.config import settings
from ai_sub.models import FilteredBlogArticle, FilteredRelease
from ai_sub.notifier.telegram import send_telegram
from ai_sub.notifier.feishu import send_feishu

logger = logging.getLogger(__name__)


async def notify_all(release: FilteredRelease) -> None:
    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        tasks.append(asyncio.create_task(send_telegram(release)))
    if settings.feishu_enabled and settings.feishu_release_webhook_url:
        tasks.append(asyncio.create_task(send_feishu(release)))
    if not tasks:
        logger.warning("No notification channels configured")
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error("Notification failed: %s", r, exc_info=r)


async def notify_digest(text_html: str, card_elements: list[dict]) -> None:
    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        from ai_sub.notifier.telegram import send_telegram_raw
        from ai_sub.notifier.telegram_topics import get_thread_id
        thread_id = get_thread_id("release", "digest")
        tasks.append(asyncio.create_task(send_telegram_raw(text_html, message_thread_id=thread_id)))
    if settings.feishu_enabled and settings.feishu_release_webhook_url:
        from ai_sub.notifier.feishu import send_feishu_card
        tasks.append(asyncio.create_task(send_feishu_card(
            title="AI Daily Digest",
            header_color="blue",
            elements=card_elements,
        )))
    if not tasks:
        logger.warning("No notification channels configured for digest")
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error("Digest notification failed: %s", r, exc_info=r)


async def notify_blog(article: FilteredBlogArticle) -> None:
    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        from ai_sub.notifier.telegram import send_telegram_blog
        tasks.append(asyncio.create_task(send_telegram_blog(article)))
    if settings.feishu_enabled and settings.feishu_blog_webhook_url:
        from ai_sub.notifier.feishu import send_feishu_blog
        tasks.append(asyncio.create_task(send_feishu_blog(article)))
    if not tasks:
        logger.debug("No blog notification channels configured")
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error("Blog notification failed: %s", r, exc_info=r)


async def notify_blog_digest(text_html: str, card_elements: list[dict]) -> None:
    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        from ai_sub.notifier.telegram import send_telegram_raw
        from ai_sub.notifier.telegram_topics import get_thread_id
        thread_id = get_thread_id("blog", "digest")
        tasks.append(asyncio.create_task(
            send_telegram_raw(text_html, message_thread_id=thread_id)
        ))
    if settings.feishu_enabled and settings.feishu_blog_webhook_url:
        from ai_sub.notifier.feishu import send_feishu_blog_card
        tasks.append(asyncio.create_task(send_feishu_blog_card(
            title="\U0001f4d6 AI \u7f16\u7a0b\u535a\u5ba2\u6bcf\u65e5\u7cbe\u9009",
            header_color="purple",
            elements=card_elements,
        )))
    if not tasks:
        logger.debug("No blog digest notification channels configured")
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error("Blog digest notification failed: %s", r, exc_info=r)
