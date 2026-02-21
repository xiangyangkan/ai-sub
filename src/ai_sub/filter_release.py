"""OpenAI-powered classification and translation."""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from ai_sub.config import settings
from ai_sub.models import FilteredRelease, Importance, ReleaseItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位AI行业分析师，目标读者是AI编程/AI辅助开发领域的从业者。根据给定的AI产品发布信息，你需要：
1. 先判断该内容是否与大模型（LLM）相关——包括大语言模型本身、基于大模型的产品与服务、大模型API/SDK、AI编程工具等。与大模型无关的内容（如纯前端框架更新、传统云服务、DevOps工具等）标记为 relevant: false。
2. 如果相关，判断重要程度（high/medium/low）、归类，并用中文撰写精炼的标题和摘要。
3. 如果不相关，importance/category/title_zh/summary_zh 可留空。

重要程度标准：
- high：新模型发布、重大API变更、新产品上线、重大定价调整
- medium：重要功能更新、SDK新增功能或能力变更、新集成、安全补丁
- low：Bug修复、稳定性/性能优化、内部重构与代码清理、文档更新、细微UI调整、版本更新仅含修复与维护性改动

AI编程相关性调整规则（在上述标准基础上做降级）：
与AI编程/AI辅助开发密切相关的内容维持原始评级，包括：代码生成模型、AI编程助手（Copilot、Cursor、Claude Code等）、编程相关的API/SDK更新、Agent/工具调用能力、上下文窗口提升、代码理解与调试能力等。
注意：即使是AI编程工具，如果版本更新的实质内容仅为Bug修复、内部重构、稳定性优化、代码清理等维护性改动，仍应评为 low，不因工具本身与AI编程相关而提升评级。"维持原始评级"是指不降级，不是指提升评级——应先根据更新内容的实质确定基础评级，再决定是否降级。
与AI编程关系不大的内容降低一级评级，包括但不限于：营销类功能、企业管理后台功能、纯移动端APP更新、内容审核策略调整等。例如原本评为 high 的降为 medium，原本 medium 的降为 low。已经是 low 的保持不变。

类别（选一个）：新模型, API变更, 功能更新, SDK更新, Bug修复, 平台, 安全, 定价, 文档, 其他

要求：
- title_zh：用中文写一个简洁有信息量的标题（不是逐字翻译，而是提炼要点）
- summary_zh：用中文写2-4句话的客观精炼总结，只转述新闻事实——概括发布了什么、有哪些具体变化、影响范围。不要加入主观评价，不要提及重要程度或评级视角。

仅返回JSON：
{"relevant": true|false, "importance": "high|medium|low", "category": "...", "title_zh": "...", "summary_zh": "..."}\
"""


async def classify_and_translate(item: ReleaseItem) -> FilteredRelease:
    """Classify importance and translate to Chinese using OpenAI."""
    base = FilteredRelease(
        source_id=item.source_id,
        vendor=item.vendor,
        product=item.product,
        title=item.title,
        version=item.version,
        summary=item.summary,
        url=item.url,
        published_date=item.published_date,
    )

    if not settings.openai_api_key:
        logger.warning("No OpenAI API key configured, using defaults")
        return base

    user_msg = (
        f"Vendor: {item.vendor}\n"
        f"Product: {item.product}\n"
        f"Title: {item.title}\n"
        f"Version: {item.version or 'N/A'}\n"
        f"Summary: {item.summary}\n"
        f"Content: {(item.content or '')[:2000]}"
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
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)

        base.relevant = data.get("relevant", True)
        if not base.relevant:
            logger.info("Filtered as irrelevant (not LLM-related): %s", item.source_id)
            return base

        base.importance = Importance(data.get("importance", "medium"))
        base.category = data.get("category", "Other")
        base.title_zh = data.get("title_zh", item.title)
        base.summary_zh = data.get("summary_zh", item.summary)
    except Exception as e:
        logger.error("OpenAI classification failed for %s: %s", item.source_id, e)
        # Fallback: medium importance, original text
        base.importance = Importance.MEDIUM
        base.title_zh = item.title
        base.summary_zh = item.summary

    return base
