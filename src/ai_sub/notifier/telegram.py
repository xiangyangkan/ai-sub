"""Telegram Bot API notifications."""
from __future__ import annotations

import html
import logging
from functools import lru_cache

import httpx

from ai_sub.config import settings
from ai_sub.models import FilteredBlogArticle, FilteredRelease, Importance
from ai_sub.notifier.telegram_topics import get_thread_id

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=15, write=10, pool=10))

# Telegram message length limit
TG_MAX_LENGTH = 4096


def _split_html_message(text: str, max_length: int = TG_MAX_LENGTH) -> list[str]:
    """Split a long HTML message into chunks that fit Telegram's limit.

    Splits at line boundaries to avoid breaking HTML tags.
    """
    if len(text) <= max_length:
        return [text]

    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        # +1 for the newline character that joins lines
        added_len = len(line) + (1 if current else 0)
        if current and current_len + added_len > max_length:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += added_len

    if current:
        chunks.append("\n".join(current))

    # Add page indicators if there are multiple chunks
    if len(chunks) > 1:
        total = len(chunks)
        chunks = [f"{chunk}\n\n({i + 1}/{total})" for i, chunk in enumerate(chunks)]

    return chunks


IMPORTANCE_LABEL = {
    Importance.HIGH: "\U0001f525 \u3010\u91cd\u8981\u3011",      # 🔥【重要】
    Importance.MEDIUM: "\u2705 \u3010\u5173\u6ce8\u3011",        # ✅【关注】
    Importance.LOW: "\u2139\ufe0f \u3010\u4e86\u89e3\u3011",     # ℹ️【了解】
}


def _format_release(r: FilteredRelease) -> str:
    label = IMPORTANCE_LABEL.get(r.importance, IMPORTANCE_LABEL[Importance.MEDIUM])
    e = html.escape
    title = r.title_zh or r.title
    summary = r.summary_zh or r.summary
    meta = f"{e(r.vendor)} · {e(r.product)}"
    if r.version:
        meta += f" · {e(r.version)}"

    lines = [
        f"{label}",
        f"<b>{e(title)}</b>",
        f"<i>{meta}</i>",
        "",
        e(summary),
        "",
        f'<a href="{e(r.url)}">查看原文</a>',
    ]
    return "\n".join(lines)


async def send_telegram(release: FilteredRelease) -> None:
    text = _format_release(release)
    thread_id = get_thread_id("release", release.importance.value)
    await send_telegram_raw(text, message_thread_id=thread_id)


async def send_telegram_raw(
    text_html: str,
    chat_id: str | None = None,
    message_thread_id: int | None = None,
) -> None:
    chunks = _split_html_message(text_html)
    if len(chunks) > 1:
        logger.info("Message too long (%d chars), splitting into %d parts", len(text_html), len(chunks))

    target_chat_id = chat_id or settings.telegram_chat_id
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    for chunk in chunks:
        payload = {
            "chat_id": target_chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        resp = await _get_client().post(url, json=payload)
        if resp.status_code != 200:
            logger.error("Telegram API error %d: %s", resp.status_code, resp.text)
            resp.raise_for_status()

    logger.info("Telegram notification sent (%d part(s))", len(chunks))


def _format_blog_article(a: FilteredBlogArticle) -> str:
    label = IMPORTANCE_LABEL.get(a.importance, IMPORTANCE_LABEL[Importance.MEDIUM])
    e = html.escape
    title = a.title_zh or a.title
    summary = a.summary_zh or a.summary
    cat_tag = f"[{e(a.ai_category)}] " if a.ai_category else ""
    meta = e(a.blog_name)

    lines = [
        f"{label}",
        f"<b>{cat_tag}{e(title)}</b>",
        f"<i>{meta}</i>",
        "",
        e(summary),
        "",
        f'<a href="{e(a.url)}">\u67e5\u770b\u539f\u6587</a>',
    ]
    return "\n".join(lines)


async def send_telegram_blog(article: FilteredBlogArticle) -> None:
    text = _format_blog_article(article)
    source = article.notify_as if article.notify_as in ("blog", "release") else "blog"
    thread_id = get_thread_id(source, article.importance.value)
    await send_telegram_raw(text, message_thread_id=thread_id)
