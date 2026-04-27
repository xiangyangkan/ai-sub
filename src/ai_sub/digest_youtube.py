"""Daily digest for YouTube videos: group by channel, show ai_category."""
from __future__ import annotations

import html
import logging
from collections import defaultdict

from ai_sub.models import Importance, IMPORTANCE_ORDER

logger = logging.getLogger(__name__)

IMPORTANCE_EMOJI = {
    "high": "\U0001f525",     # fire
    "medium": "✅",       # check
    "low": "ℹ️",    # info
}


def build_telegram_youtube_digest(videos: list[dict]) -> str:
    if not videos:
        return ""

    by_channel: dict[str, list[dict]] = defaultdict(list)
    for v in videos:
        by_channel[v["channel_name"]].append(v)

    e = html.escape
    lines = ["\U0001f3ac <b>AI 视频每日精选</b>", ""]

    for channel, items in sorted(by_channel.items()):
        items.sort(key=lambda x: IMPORTANCE_ORDER.get(
            Importance(x.get("importance", "medium")), 1
        ))
        lines.append(f"<b>{e(channel)}</b>")
        for v in items:
            emoji = IMPORTANCE_EMOJI.get(v.get("importance", "medium"), "✅")
            title = e(v.get("title_zh") or v.get("title", ""))
            url = v.get("url", "")
            summary = e((v.get("summary_zh") or "")[:100])
            lines.append(f'{emoji} <a href="{e(url)}">{title}</a>')
            if summary:
                lines.append(f"    {summary}")
        lines.append("")

    lines.append(f"共 {len(videos)} 个视频")
    return "\n".join(lines)


def build_feishu_youtube_digest_elements(videos: list[dict]) -> list[dict]:
    if not videos:
        return []

    by_channel: dict[str, list[dict]] = defaultdict(list)
    for v in videos:
        by_channel[v["channel_name"]].append(v)

    elements: list[dict] = []

    for channel, items in sorted(by_channel.items()):
        items.sort(key=lambda x: IMPORTANCE_ORDER.get(
            Importance(x.get("importance", "medium")), 1
        ))
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{channel}**"},
        })

        video_lines = []
        for v in items:
            emoji = IMPORTANCE_EMOJI.get(v.get("importance", "medium"), "✅")
            title = v.get("title_zh") or v.get("title", "")
            url = v.get("url", "")
            summary = (v.get("summary_zh") or "")[:100]
            video_lines.append(f"{emoji} [{title}]({url})")
            if summary:
                video_lines.append(f"  {summary}")

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(video_lines)},
        })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"共 {len(videos)} 个视频"},
    })
    return elements
