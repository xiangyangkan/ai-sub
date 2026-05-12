"""Generate summary card images using Playwright (HTML/CSS → screenshot)."""
from __future__ import annotations

import html
import logging

from playwright.async_api import async_playwright, Browser

from ai_sub.config import settings
from ai_sub.models import FilteredYouTubeVideo, Importance

logger = logging.getLogger(__name__)

_browser: Browser | None = None

IMPORTANCE_STYLES = {
    Importance.HIGH: {"accent": "#E53935", "badge_bg": "#FFEBEE", "badge_text": "#C62828", "label": "重要"},
    Importance.MEDIUM: {"accent": "#1E88E5", "badge_bg": "#E3F2FD", "badge_text": "#1565C0", "label": "关注"},
    Importance.LOW: {"accent": "#43A047", "badge_bg": "#E8F5E9", "badge_text": "#2E7D32", "label": "了解"},
}


async def _get_browser() -> Browser:
    global _browser
    if _browser is None or not _browser.is_connected():
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
    return _browser


def _build_html(video: FilteredYouTubeVideo) -> str:
    e = html.escape
    style = IMPORTANCE_STYLES.get(video.importance, IMPORTANCE_STYLES[Importance.MEDIUM])

    title = e(video.title_zh or video.title)
    summary = e(video.summary_zh or video.description[:500])
    channel = e(video.channel_name)
    category = e(video.ai_category) if video.ai_category else ""
    date_str = video.published_date.strftime("%Y-%m-%d") if video.published_date else ""

    points_html = ""
    if video.key_points:
        points = [p.strip() for p in video.key_points.strip().split("\n") if p.strip()]
        cleaned = []
        for p in points:
            p = p.lstrip("•·-–— ")
            if p:
                cleaned.append(p)
        items = "".join(f"<li>{e(p)}</li>" for p in cleaned)
        points_html = f'<div class="section-title">要点</div><ul class="points">{items}</ul>'

    category_tag = f'<span class="tag category">{category}</span>' if category else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}
body {{
    width: 1200px;
    font-family: "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
                 "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
                 -apple-system, sans-serif;
    background: transparent;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}}
.card {{
    width: 1200px;
    background: #ffffff;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.05);
}}
.accent-bar {{
    height: 5px;
    background: linear-gradient(90deg, {style["accent"]}, {style["accent"]}88);
}}
.content {{
    padding: 44px 56px 36px;
}}
.header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
}}
.tag {{
    display: inline-block;
    padding: 5px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
    letter-spacing: 0.02em;
}}
.badge {{
    background: {style["badge_bg"]};
    color: {style["badge_text"]};
}}
.category {{
    background: #F3F4F6;
    color: #4B5563;
    font-weight: 500;
}}
.channel {{
    margin-left: auto;
    font-size: 14px;
    color: #9CA3AF;
    letter-spacing: 0.01em;
}}
.title {{
    font-size: 28px;
    font-weight: 700;
    color: #1A1A2E;
    line-height: 1.5;
    margin-bottom: 24px;
    letter-spacing: -0.01em;
}}
.divider {{
    height: 1px;
    background: linear-gradient(90deg, #E5E7EB, transparent);
    margin: 0 0 24px 0;
}}
.summary {{
    font-size: 16px;
    color: #374151;
    line-height: 2;
    margin-bottom: 28px;
    text-align: justify;
    letter-spacing: 0.02em;
}}
.section-title {{
    font-size: 13px;
    font-weight: 600;
    color: #9CA3AF;
    margin-bottom: 14px;
    letter-spacing: 0.08em;
}}
.points {{
    list-style: none;
    padding: 0;
    margin-bottom: 28px;
}}
.points li {{
    position: relative;
    padding-left: 18px;
    font-size: 14px;
    color: #4B5563;
    line-height: 1.9;
    margin-bottom: 10px;
    letter-spacing: 0.01em;
}}
.points li::before {{
    content: "";
    position: absolute;
    left: 0;
    top: 10px;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: {style["accent"]};
    opacity: 0.8;
}}
.footer {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 20px;
    border-top: 1px solid #F3F4F6;
    margin-top: 12px;
}}
.date {{
    font-size: 13px;
    color: #D1D5DB;
    letter-spacing: 0.02em;
}}
.brand {{
    font-size: 13px;
    color: #E5E7EB;
    font-weight: 500;
    letter-spacing: 0.05em;
}}
</style>
</head>
<body>
<div class="card">
    <div class="accent-bar"></div>
    <div class="content">
        <div class="header">
            <span class="tag badge">{style["label"]}</span>
            {category_tag}
            <span class="channel">{channel}</span>
        </div>
        <h1 class="title">{title}</h1>
        <div class="divider"></div>
        <p class="summary">{summary}</p>
        {points_html}
        <div class="footer">
            <span class="date">{date_str}</span>
            <span class="brand">AI Sub</span>
        </div>
    </div>
</div>
</body>
</html>"""


async def render_youtube_card(video: FilteredYouTubeVideo) -> bytes | None:
    """Render a YouTube video summary card. Returns PNG bytes or None on failure."""
    try:
        browser = await _get_browser()
        page = await browser.new_page(viewport={"width": 1200, "height": 800}, device_scale_factor=2)
        html_content = _build_html(video)
        await page.set_content(html_content, wait_until="load")
        card = page.locator(".card")
        png_bytes = await card.screenshot(type="png")
        await page.close()
        return png_bytes
    except Exception as e:
        logger.error("Card rendering failed: %s", e, exc_info=True)
        return None
