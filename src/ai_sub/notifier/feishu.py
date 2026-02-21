"""Feishu webhook notifications using Interactive Card format."""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from ai_sub.config import settings
from ai_sub.models import FilteredBlogArticle, FilteredRelease, Importance

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=15, write=10, pool=10))

IMPORTANCE_COLOR = {
    Importance.HIGH: "red",
    Importance.MEDIUM: "yellow",
    Importance.LOW: "green",
}


IMPORTANCE_LABEL = {
    Importance.HIGH: "\U0001f525 \u91cd\u8981",     # 🔥 重要
    Importance.MEDIUM: "\u2705 \u5173\u6ce8",       # ✅ 关注
    Importance.LOW: "\u2139\ufe0f \u4e86\u89e3",    # ℹ️ 了解
}


def _build_card(r: FilteredRelease) -> dict:
    color = IMPORTANCE_COLOR.get(r.importance, "yellow")
    label = IMPORTANCE_LABEL.get(r.importance, IMPORTANCE_LABEL[Importance.MEDIUM])
    title = r.title_zh or r.title
    summary = r.summary_zh or r.summary

    meta = f"{r.vendor} · {r.product}"
    if r.version:
        meta += f" · {r.version}"

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{label}** | *{meta}*"},
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": summary},
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看原文"},
                    "url": r.url,
                    "type": "default",
                }
            ],
        },
    ]

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        },
    }


async def send_feishu(release: FilteredRelease) -> None:
    card = _build_card(release)
    await _post_webhook(card)


async def send_feishu_card(
    title: str, header_color: str, elements: list[dict]
) -> None:
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": header_color,
            },
            "elements": elements,
        },
    }
    await _post_webhook(payload)


async def _post_webhook(payload: dict, webhook_url: str | None = None) -> None:
    url = webhook_url or settings.feishu_release_webhook_url
    resp = await _get_client().post(url, json=payload)
    result = resp.json()
    if result.get("code") != 0:
        logger.error("Feishu webhook error: %s", result)
        raise RuntimeError(f"Feishu error: {result}")
    logger.info("Feishu notification sent")


def _build_blog_card(a: FilteredBlogArticle) -> dict:
    color = IMPORTANCE_COLOR.get(a.importance, "yellow")
    label = IMPORTANCE_LABEL.get(a.importance, IMPORTANCE_LABEL[Importance.MEDIUM])
    title = a.title_zh or a.title
    summary = a.summary_zh or a.summary
    cat_tag = f"[{a.ai_category}] " if a.ai_category else ""
    meta = a.blog_name

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{label}** | {cat_tag}*{meta}*"},
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": summary},
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "\u67e5\u770b\u539f\u6587"},
                    "url": a.url,
                    "type": "default",
                }
            ],
        },
    ]

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        },
    }


async def send_feishu_blog(article: FilteredBlogArticle) -> None:
    card = _build_blog_card(article)
    webhook = (settings.feishu_release_webhook_url
               if article.notify_as == "release"
               else settings.feishu_blog_webhook_url)
    await _post_webhook(card, webhook_url=webhook)


async def send_feishu_blog_card(
    title: str, header_color: str, elements: list[dict]
) -> None:
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": header_color,
            },
            "elements": elements,
        },
    }
    await _post_webhook(payload, webhook_url=settings.feishu_blog_webhook_url)
