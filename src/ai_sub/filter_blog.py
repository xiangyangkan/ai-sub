"""LLM-powered classification for blog articles (AI programming relevance)."""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from ai_sub.config import settings
from ai_sub.models import BlogArticle, FilteredBlogArticle, Importance

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位AI编程领域分析师，目标读者是AI编程/AI辅助开发领域的从业者。根据给定的博客文章信息，你需要：

1. 判断该文章是否与 **AI编程/AI辅助开发** 相关。
   相关主题包括：
   - AI编程工具（Copilot、Cursor、Claude Code、Windsurf等）
   - Agent开发（LLM Agent框架、工具调用、MCP等）
   - LLM API/SDK应用开发
   - RAG实践（检索增强生成的工程实现）
   - Prompt Engineering的编程应用
   - AI代码生成、代码审查、自动测试
   - 模型微调/部署的工程实践

   不相关主题：
   - 纯学术论文（无工程实践）
   - 纯营销内容
   - 非编程的AI应用（如AI绘画、AI音乐等，除非涉及开发工具）
   - 传统软件工程（无AI相关）
   - 一般技术博客（数据库、前端框架、DevOps等，除非与AI编程结合）

2. 如果相关，评估重要性：
   - high：深度原创内容、重要工具发布、有独到见解的技术分析
   - medium：有价值的技术分享、教程、经验总结
   - low：简单转述、新闻汇总、浅层介绍

3. 分类（选一个）：AI编程工具, Agent开发, LLM应用开发, RAG与检索, Prompt工程, 模型与推理, 开发实践, 行业动态, 其他

4. 用中文撰写标题和摘要：
   - title_zh：简洁有信息量的中文标题
   - summary_zh：2-4句话的客观精炼总结

仅返回JSON：
{"relevant": true|false, "importance": "high|medium|low", "ai_category": "...", "title_zh": "...", "summary_zh": "..."}\
"""


async def classify_blog_article(article: BlogArticle) -> FilteredBlogArticle:
    """Classify a blog article for AI programming relevance using LLM."""
    base = FilteredBlogArticle(
        source_id=article.source_id,
        blog_name=article.blog_name,
        category=article.category,
        title=article.title,
        url=article.url,
        summary=article.summary,
        published_date=article.published_date,
        relevant=False,
        notify_as=article.notify_as,
    )

    if not settings.openai_api_key:
        logger.warning("No OpenAI API key configured, skipping blog classification")
        return base

    user_msg = (
        f"Blog: {article.blog_name}\n"
        f"Category: {article.category}\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary}\n"
        f"Content: {(article.content or '')[:3000]}"
    )

    try:
        kwargs = {}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        client = AsyncOpenAI(api_key=settings.openai_api_key, **kwargs)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)

        base.relevant = data.get("relevant", False)
        if not base.relevant:
            logger.debug("Blog article not AI-programming related: %s", article.title)
            return base

        base.importance = Importance(data.get("importance", "medium"))
        base.ai_category = data.get("ai_category", "")
        base.title_zh = data.get("title_zh", article.title)
        base.summary_zh = data.get("summary_zh", article.summary)
    except Exception as e:
        logger.error("Blog classification failed for %s: %s", article.source_id, e)
        base.relevant = False

    return base
