"""LLM-powered classification for blog articles (AI programming relevance)."""
from __future__ import annotations

import logging

from ai_sub.config import settings
from ai_sub.llm import chat_json
from ai_sub.models import BlogArticle, FilteredBlogArticle, Importance

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位AI行业分析师。根据给定的博客文章信息，你需要：

1. 判断该文章是否与 **AI / 大模型** 相关。
   相关主题包括（但不限于）：
   - 大语言模型（LLM）发布、评测、能力分析
   - AI编程工具（Copilot、Cursor、Claude Code、Windsurf等）
   - Agent开发（LLM Agent框架、工具调用、MCP等）
   - LLM API/SDK应用开发
   - RAG实践（检索增强生成）
   - Prompt Engineering
   - AI代码生成、代码审查、自动测试
   - 模型训练、微调、部署、推理优化
   - AI产品设计、AI应用案例
   - AI行业动态、公司战略、从业者访谈
   - 多模态模型、AI图像/视频/音频生成
   - AI安全、对齐、伦理

   不相关主题：
   - 与AI/大模型完全无关的纯软件工程内容
   - 纯营销/推广内容（无技术实质）
   - 加密货币、金融等非AI话题

2. 如果相关，评估重要性：
   - high：深度原创内容、重要模型/工具发布、有独到见解的技术分析
   - medium：有价值的技术分享、教程、经验总结
   - low：简单转述、新闻汇总、浅层介绍

3. 分类（选一个）：AI编程工具, Agent开发, LLM应用开发, RAG与检索, Prompt工程, 模型与推理, 开发实践, AI应用, 行业动态, 其他

4. 用中文撰写标题和摘要：
   - title_zh：简洁有信息量的中文标题
   - summary_zh：2-4句话的客观精炼总结

仅返回JSON：
{"relevant": true|false, "importance": "high|medium|low", "ai_category": "...", "title_zh": "...", "summary_zh": "..."}\
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "importance": {"type": "string", "enum": ["high", "medium", "low"]},
        "ai_category": {"type": "string"},
        "title_zh": {"type": "string"},
        "summary_zh": {"type": "string"},
    },
    "required": ["relevant", "importance", "ai_category", "title_zh", "summary_zh"],
    "additionalProperties": False,
}


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

    if not settings.openai_api_key and not settings.anthropic_api_key:
        logger.warning("No LLM API key configured, skipping blog classification")
        return base

    user_msg = (
        f"Blog: {article.blog_name}\n"
        f"Category: {article.category}\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary}\n"
        f"Content: {(article.content or '')[:3000]}"
    )

    try:
        data = await chat_json(SYSTEM_PROMPT, user_msg, output_schema=OUTPUT_SCHEMA)

        base.relevant = data.get("relevant", False)
        if not base.relevant:
            logger.info("Blog article not AI-related: %s", article.title)
            return base

        base.importance = Importance(data.get("importance", "medium"))
        base.ai_category = data.get("ai_category", "")
        base.title_zh = data.get("title_zh", article.title)
        base.summary_zh = data.get("summary_zh", article.summary)
    except Exception as e:
        logger.error("Blog classification failed for %s: %s", article.source_id, e)
        base.relevant = False

    return base
