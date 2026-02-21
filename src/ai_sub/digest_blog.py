"""Daily digest for blog articles: group by blog_name, show ai_category."""
from __future__ import annotations

import html
import logging
from collections import defaultdict

from ai_sub.models import Importance, IMPORTANCE_ORDER

logger = logging.getLogger(__name__)

IMPORTANCE_EMOJI = {
    "high": "\U0001f525",     # 🔥
    "medium": "\u2705",       # ✅
    "low": "\u2139\ufe0f",    # ℹ️
}


def build_telegram_blog_digest(articles: list[dict]) -> str:
    if not articles:
        return ""

    by_blog: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_blog[a["blog_name"]].append(a)

    e = html.escape
    lines = ["\U0001f4d6 <b>AI \u7f16\u7a0b\u535a\u5ba2\u6bcf\u65e5\u7cbe\u9009</b>", ""]

    for blog_name, items in sorted(by_blog.items()):
        items.sort(key=lambda x: IMPORTANCE_ORDER.get(
            Importance(x.get("importance", "medium")), 1
        ))
        lines.append(f"<b>{e(blog_name)}</b>")
        for a in items:
            emoji = IMPORTANCE_EMOJI.get(a.get("importance", "medium"), "\u2705")
            title = e(a.get("title_zh") or a.get("title", ""))
            url = a.get("url", "")
            lines.append(f"{emoji} <a href=\"{e(url)}\">{title}</a>")
        lines.append("")

    lines.append(f"\u5171 {len(articles)} \u7bc7\u6587\u7ae0")
    return "\n".join(lines)


def build_feishu_blog_digest_elements(articles: list[dict]) -> list[dict]:
    if not articles:
        return []

    by_blog: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_blog[a["blog_name"]].append(a)

    elements: list[dict] = []

    for blog_name, items in sorted(by_blog.items()):
        items.sort(key=lambda x: IMPORTANCE_ORDER.get(
            Importance(x.get("importance", "medium")), 1
        ))
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{blog_name}**"},
        })

        article_lines = []
        for a in items:
            emoji = IMPORTANCE_EMOJI.get(a.get("importance", "medium"), "\u2705")
            title = a.get("title_zh") or a.get("title", "")
            url = a.get("url", "")
            article_lines.append(f"{emoji} [{title}]({url})")

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(article_lines)},
        })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"\u5171 {len(articles)} \u7bc7\u6587\u7ae0"},
    })
    return elements
