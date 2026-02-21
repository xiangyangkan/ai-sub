"""Daily digest: group by vendor, sort by importance."""
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


def build_telegram_digest(releases: list[dict]) -> str:
    if not releases:
        return ""

    by_vendor: dict[str, list[dict]] = defaultdict(list)
    for r in releases:
        by_vendor[r["vendor"]].append(r)

    e = html.escape
    lines = ["\U0001f4cb <b>AI 每日动态</b>", ""]

    for vendor, items in sorted(by_vendor.items()):
        items.sort(key=lambda x: IMPORTANCE_ORDER.get(
            Importance(x.get("importance", "medium")), 1
        ))
        lines.append(f"<b>{e(vendor.upper())}</b>")
        for r in items:
            emoji = IMPORTANCE_EMOJI.get(r.get("importance", "medium"), "\u2705")
            title = e(r.get("title_zh") or r.get("title", ""))
            url = r.get("url", "")
            lines.append(f"{emoji} <a href=\"{e(url)}\">{title}</a>")
        lines.append("")

    lines.append(f"共 {len(releases)} 条更新")
    return "\n".join(lines)


def build_feishu_digest_elements(releases: list[dict]) -> list[dict]:
    if not releases:
        return []

    by_vendor: dict[str, list[dict]] = defaultdict(list)
    for r in releases:
        by_vendor[r["vendor"]].append(r)

    elements: list[dict] = []

    for vendor, items in sorted(by_vendor.items()):
        items.sort(key=lambda x: IMPORTANCE_ORDER.get(
            Importance(x.get("importance", "medium")), 1
        ))
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{vendor.upper()}**"},
        })

        release_lines = []
        for r in items:
            emoji = IMPORTANCE_EMOJI.get(r.get("importance", "medium"), "\u2705")
            title = r.get("title_zh") or r.get("title", "")
            url = r.get("url", "")
            release_lines.append(f"{emoji} [{title}]({url})")

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(release_lines)},
        })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"共 {len(releases)} 条更新"},
    })
    return elements
