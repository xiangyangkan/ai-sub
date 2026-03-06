"""Unified LLM client supporting OpenAI and Anthropic."""
from __future__ import annotations

import json
import logging

from ai_sub.config import settings

logger = logging.getLogger(__name__)


async def chat_json(
    system_prompt: str,
    user_message: str,
    *,
    output_schema: dict | None = None,
) -> dict:
    """Send a chat completion request and return parsed JSON.

    Routes to OpenAI or Anthropic based on settings.llm_provider.
    """
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        return await _anthropic_chat(system_prompt, user_message, output_schema=output_schema)
    return await _openai_chat(system_prompt, user_message)


async def _openai_chat(system_prompt: str, user_message: str) -> dict:
    from openai import AsyncOpenAI

    if not settings.openai_api_key:
        raise ValueError("No OpenAI API key configured")

    kwargs = {}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    client = AsyncOpenAI(api_key=settings.openai_api_key, **kwargs)
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        reasoning_effort="none",
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


async def _anthropic_chat(
    system_prompt: str,
    user_message: str,
    *,
    output_schema: dict | None = None,
) -> dict:
    from anthropic import AsyncAnthropic

    if not settings.anthropic_api_key:
        raise ValueError("No Anthropic API key configured")

    kwargs = {}
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, **kwargs)

    create_kwargs: dict = {
        "model": settings.anthropic_model,
        "max_tokens": 65536,
        "thinking": {"type": "disabled"},
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message},
        ],
    }
    if output_schema:
        create_kwargs["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": output_schema,
            }
        }

    resp = await client.messages.create(**create_kwargs)
    raw = resp.content[0].text or "{}"
    return json.loads(raw)
