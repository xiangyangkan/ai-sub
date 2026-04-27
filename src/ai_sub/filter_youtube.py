"""LLM-powered classification and summarization for YouTube videos."""
from __future__ import annotations

import logging

from ai_sub.config import settings
from ai_sub.llm import chat_json
from ai_sub.models import FilteredYouTubeVideo, Importance, YouTubeVideo

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM_PROMPT = """\
你是一位AI编程领域分析师。根据给定的YouTube视频信息，判断该视频是否与AI编程/AI辅助开发相关。

相关主题包括：
- AI编程工具（Copilot、Cursor、Claude Code、Windsurf等）
- Agent开发（LLM Agent框架、工具调用、MCP等）
- LLM API/SDK应用开发
- RAG实践（检索增强生成的工程实现）
- Prompt Engineering的编程应用
- AI代码生成、代码审查、自动测试
- 模型微调/部署的工程实践
- 大模型发布、评测、能力分析

不相关主题：
- 纯学术论文讲解（无工程实践）
- 纯营销/推广内容
- 非编程的AI应用（AI绘画、AI音乐等，除非涉及开发工具）
- 传统软件工程（无AI相关）
- 加密货币、金融等非AI话题

如果相关，评估重要性：
- high：深度原创内容、重要工具/模型发布、有独到见解的技术分析
- medium：有价值的技术分享、教程、经验总结
- low：简单转述、新闻汇总、浅层介绍

分类（选一个）：AI编程工具, Agent开发, LLM应用开发, RAG与检索, Prompt工程, 模型与推理, 开发实践, 行业动态, 其他

仅返回JSON：
{"relevant": true|false, "importance": "high|medium|low", "ai_category": "..."}\
"""

CLASSIFY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "importance": {"type": "string", "enum": ["high", "medium", "low"]},
        "ai_category": {"type": "string"},
    },
    "required": ["relevant", "importance", "ai_category"],
    "additionalProperties": False,
}

SUMMARIZE_SYSTEM_PROMPT = """\
你是一位专业的AI技术内容编辑。根据YouTube视频的字幕文本，生成深度结构化的中文摘要。

要求：
1. title_zh：简洁有信息量的中文标题（不是逐字翻译，而是提炼核心论点）
2. summary_zh：4-8句话的深度总结。要求：
   - 第一段（2-3句）：概括视频核心主题、关键论点和最终结论
   - 第二段（2-5句）：提炼视频中最重要的洞察、方法论或实践建议，说明其价值和适用场景
   不要泛泛而谈，要包含具体的观点、数据、方法或结论
3. key_points：5-10个深度要点，每个要点一行，用"• "开头。每个要点应该：
   - 包含具体的论据、数据、案例或方法步骤（不要只写抽象概括）
   - 让读者不看视频也能获得核心信息价值
   - 涵盖视频的不同维度（观点、方法、案例、反思、建议等）

注意：
- 所有内容用中文撰写
- 保持客观，不加主观评价
- 总结应该有足够的信息密度，让读者无需观看视频也能掌握核心内容

仅返回JSON：
{"title_zh": "...", "summary_zh": "...", "key_points": "..."}\
"""

SUMMARIZE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title_zh": {"type": "string"},
        "summary_zh": {"type": "string"},
        "key_points": {"type": "string"},
    },
    "required": ["title_zh", "summary_zh", "key_points"],
    "additionalProperties": False,
}


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


async def classify_and_summarize_video(video: YouTubeVideo) -> FilteredYouTubeVideo:
    base = FilteredYouTubeVideo(
        source_id=video.source_id,
        video_id=video.video_id,
        channel_name=video.channel_name,
        category=video.category,
        title=video.title,
        url=video.url,
        description=video.description,
        published_date=video.published_date,
        relevant=False,
    )

    if not settings.openai_api_key and not settings.anthropic_api_key:
        logger.warning("No LLM API key configured, skipping video classification")
        return base

    classify_msg = (
        f"Channel: {video.channel_name}\n"
        f"Title: {video.title}\n"
        f"Description: {video.description[:500]}\n"
        f"Transcript preview: {(video.transcript or '')[:500]}"
    )

    try:
        data = await chat_json(
            CLASSIFY_SYSTEM_PROMPT, classify_msg,
            output_schema=CLASSIFY_OUTPUT_SCHEMA,
        )
        base.relevant = data.get("relevant", False)
        if not base.relevant:
            logger.debug("Video not AI-related: %s", video.title)
            return base
        base.importance = Importance(data.get("importance", "medium"))
        base.ai_category = data.get("ai_category", "")
    except Exception as e:
        logger.error("Video classification failed for %s: %s", video.source_id, e)
        base.relevant = False
        return base

    if not video.transcript:
        base.title_zh = video.title
        base.summary_zh = video.description[:500]
        return base

    if video.transcript_segments:
        transcript_with_ts = "\n".join(
            f"[{_format_time(s['start'])}] {s['text']}"
            for s in video.transcript_segments
        )
    else:
        transcript_with_ts = video.transcript

    summarize_msg = (
        f"Channel: {video.channel_name}\n"
        f"Title: {video.title}\n\n"
        f"字幕文本:\n{transcript_with_ts[:15000]}"
    )

    try:
        data = await chat_json(
            SUMMARIZE_SYSTEM_PROMPT, summarize_msg,
            output_schema=SUMMARIZE_OUTPUT_SCHEMA,
            max_tokens=4096,
        )
        base.title_zh = data.get("title_zh", video.title)
        base.summary_zh = data.get("summary_zh", "")
        base.key_points = data.get("key_points", "")
    except Exception as e:
        logger.error("Video summarization failed for %s: %s", video.source_id, e)
        base.title_zh = video.title
        base.summary_zh = video.description[:500]

    return base
