"""LLM 适配层。业务代码只依赖 LangChain 的 BaseChatModel 接口，不直接引用某家厂商的 SDK。"""

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
    """thinking=None 时使用配置中的主 Agent 设置。

    Kimi 思考模式会先生成推理过程（更慢、更多 token），只接受 temperature=1；
    关闭思考时只接受 temperature=0.6。话题路由这类简单分类任务应关闭思考。
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
