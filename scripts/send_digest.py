#!/usr/bin/env python3
"""手动触发日报总结。

用法:
    # 发送所有日报 (release + blog)，默认最近 24 小时
    python scripts/send_digest.py

    # 仅发送 release 日报
    python scripts/send_digest.py --release

    # 仅发送 blog 日报
    python scripts/send_digest.py --blog

    # 自定义时间范围（小时）
    python scripts/send_digest.py --hours 48

    # 预览模式，不实际发送
    python scripts/send_digest.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from ai_sub.config import settings
from ai_sub.digest_blog import build_feishu_blog_digest_elements, build_telegram_blog_digest
from ai_sub.digest_release import build_feishu_digest_elements, build_telegram_digest
from ai_sub.notifier import notify_blog_digest, notify_digest
from ai_sub.store_blog import get_undigested_blogs, mark_blogs_digested
from ai_sub.store_release import get_undigested, mark_digested

logger = logging.getLogger(__name__)


async def send_release_digest(hours: int, dry_run: bool) -> None:
    releases = get_undigested(since_hours=hours)
    if not releases:
        print(f"没有最近 {hours} 小时内未发送的 release 日报内容")
        return

    print(f"找到 {len(releases)} 条 release 更新")

    tg_text = build_telegram_digest(releases)
    feishu_elements = build_feishu_digest_elements(releases)

    if dry_run:
        print("\n--- Telegram 预览 ---")
        print(tg_text)
        print("--- 预览结束 ---\n")
        return

    try:
        await notify_digest(tg_text, feishu_elements)
    except Exception as e:
        print(f"Release 日报发送失败: {e}")
        return
    mark_digested([r["source_id"] for r in releases])
    print(f"Release 日报已发送，共 {len(releases)} 条更新")


async def send_blog_digest(hours: int, dry_run: bool) -> None:
    articles = get_undigested_blogs(since_hours=hours)
    if not articles:
        print(f"没有最近 {hours} 小时内未发送的 blog 日报内容")
        return

    print(f"找到 {len(articles)} 篇博客文章")

    tg_text = build_telegram_blog_digest(articles)
    feishu_elements = build_feishu_blog_digest_elements(articles)

    if dry_run:
        print("\n--- Telegram 预览 ---")
        print(tg_text)
        print("--- 预览结束 ---\n")
        return

    try:
        await notify_blog_digest(tg_text, feishu_elements)
    except Exception as e:
        print(f"Blog 日报发送失败: {e}")
        return
    mark_blogs_digested([a["source_id"] for a in articles])
    print(f"Blog 日报已发送，共 {len(articles)} 篇文章")


async def main() -> None:
    parser = argparse.ArgumentParser(description="手动触发日报总结")
    parser.add_argument("--release", action="store_true", help="仅发送 release 日报")
    parser.add_argument("--blog", action="store_true", help="仅发送 blog 日报")
    parser.add_argument("--hours", type=int, default=24, help="回溯时间范围（小时），默认 24")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际发送通知")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 未指定 --release 或 --blog 时，两个都发
    send_all = not args.release and not args.blog

    if args.dry_run:
        print("=== 预览模式 ===\n")

    if send_all or args.release:
        await send_release_digest(args.hours, args.dry_run)

    if send_all or args.blog:
        await send_blog_digest(args.hours, args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
