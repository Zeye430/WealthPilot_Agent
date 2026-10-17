"""LLM 适配层。业务代码只依赖 LangChain 的 BaseChatModel 接口，不直接引用某家厂商的 SDK。"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


class LLMNotConfiguredError(RuntimeError):
    pass


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    if not settings.llm_api_key.get_secret_value():
        raise LLMNotConfiguredError("未配置 LLM_API_KEY，请在仓库根目录 .env 中填写")
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
