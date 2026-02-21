from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel


class Importance(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


IMPORTANCE_ORDER = {Importance.HIGH: 0, Importance.MEDIUM: 1, Importance.LOW: 2}


class ReleaseItem(BaseModel):
    source_id: str  # "{vendor}:{release_id}"
    vendor: str
    product: str
    title: str
    version: str | None = None
    url: str
    summary: str
    published_date: datetime | None = None
    content: str | None = None  # Full content for OpenAI (not stored)


class FilteredRelease(BaseModel):
    source_id: str
    vendor: str
    product: str
    title: str
    version: str | None = None
    url: str
    summary: str
    published_date: datetime | None = None
    relevant: bool = True  # 是否与大模型相关
    importance: Importance = Importance.MEDIUM
    category: str = "Other"
    title_zh: str = ""
    summary_zh: str = ""


class BlogArticle(BaseModel):
    """RSS 抓取的原始博客文章"""
    source_id: str          # "blog:{feed_slug}:{entry_hash}"
    blog_name: str          # 来自 OPML 的 title
    category: str           # 来自 OPML 的父级分类
    title: str
    url: str
    summary: str
    published_date: datetime | None = None
    content: str | None = None  # 用于 LLM 分类，不入库
    notify_as: str = "blog"  # "blog" 或 "release"，控制通知路由


class FilteredBlogArticle(BaseModel):
    """LLM 过滤后的博客文章"""
    source_id: str
    blog_name: str
    category: str
    title: str
    url: str
    summary: str
    published_date: datetime | None = None
    relevant: bool = True
    importance: Importance = Importance.MEDIUM
    ai_category: str = ""     # "AI编程工具", "Agent开发", "LLM应用开发" 等
    title_zh: str = ""
    summary_zh: str = ""
    notify_as: str = "blog"   # "blog" 或 "release"，控制通知路由
