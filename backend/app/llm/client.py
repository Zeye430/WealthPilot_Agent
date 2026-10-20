"""LLM adapter. Business code depends only on LangChain's BaseChatModel interface, never on a
vendor SDK directly."""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


class LLMNotConfiguredError(RuntimeError):
    pass


def get_chat_model(
    settings: Settings | None = None,
    *,
    thinking: bool | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """thinking=None uses the main-agent setting from config.

    Kimi's thinking mode first generates reasoning (slower, more tokens) and only accepts
    temperature=1;
    with thinking off it only accepts temperature=0.6. Simple classification such as topic routing
    should run without thinking.
    """
    settings = settings or get_settings()
    if not settings.llm_api_key.get_secret_value():
        raise LLMNotConfiguredError("未配置 LLM_API_KEY，请在仓库根目录 .env 中填写")
    if thinking is None:
        thinking = settings.llm_agent_thinking
    extra_body = None if thinking else {"thinking": {"type": "disabled"}}
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature if thinking else settings.llm_temperature_no_thinking,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_tokens=max_tokens,
        extra_body=extra_body,
    )
