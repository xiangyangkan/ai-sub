"""Telegram Forum Topics management.

Creates and caches forum topics for routing messages by source × importance.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from ai_sub.config import settings

logger = logging.getLogger(__name__)

# Topic definitions: key -> (display name, icon_color)
# icon_color values: 0x6FB9F0 blue, 0xFFD67E yellow, 0xCB86DB purple,
#                    0x8EEE98 green, 0xFF93B2 pink, 0xFB6F5F red
TOPIC_DEFS: dict[str, tuple[str, int]] = {
    "release_high":   ("AI新闻 - 重要",     0xFB6F5F),  # red
    "release_medium": ("AI新闻 - 关注",     0x6FB9F0),  # blue
    "release_low":    ("AI新闻 - 了解",     0x8EEE98),  # green
    "release_digest": ("AI新闻 - 每日摘要", 0xFFD67E),  # yellow
    "blog_high":      ("AI博客 - 重要",       0xFB6F5F),  # red
    "blog_medium":    ("AI博客 - 关注",       0x6FB9F0),  # blue
    "blog_digest":    ("AI博客 - 每日摘要",   0xCB86DB),  # purple
}

_topic_cache: dict[str, int] = {}


def _topics_path() -> Path:
    return Path(settings.telegram_topics_path)


def _load_topics() -> dict[str, int]:
    p = _topics_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_topics(data: dict[str, int]) -> None:
    p = _topics_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def _create_forum_topic(name: str, icon_color: int) -> int:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/createForumTopic"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "name": name,
        "icon_color": icon_color,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.error("createForumTopic failed %d: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        data = resp.json()
    thread_id: int = data["result"]["message_thread_id"]
    logger.info("Created Telegram topic '%s' -> thread_id=%d", name, thread_id)
    return thread_id


async def ensure_topics() -> None:
    """Load or create all forum topics. Call once at startup."""
    global _topic_cache

    if not settings.telegram_chat_id or not settings.telegram_bot_token:
        logger.warning("Telegram not configured, skipping topic creation")
        return

    saved = _load_topics()
    missing = {k: v for k, v in TOPIC_DEFS.items() if k not in saved}

    if not missing:
        logger.info("All %d Telegram topics already exist", len(TOPIC_DEFS))
        _topic_cache = saved
        return

    logger.info("Creating %d missing Telegram topics...", len(missing))
    for key, (name, color) in missing.items():
        thread_id = await _create_forum_topic(name, color)
        saved[key] = thread_id

    _save_topics(saved)
    _topic_cache = saved
    logger.info("Telegram topics ready (%d total)", len(saved))


def get_thread_id(source: str, importance: str) -> int | None:
    """Return the message_thread_id for a source × importance combination.

    Args:
        source: "release" or "blog"
        importance: "high", "medium", "low", or "digest"
    """
    key = f"{source}_{importance}"
    tid = _topic_cache.get(key)
    if tid is None and not _topic_cache:
        # Cache empty — try loading from file
        _topic_cache.update(_load_topics())
        tid = _topic_cache.get(key)
    if tid is None:
        logger.warning("No thread_id for key '%s'", key)
    return tid
