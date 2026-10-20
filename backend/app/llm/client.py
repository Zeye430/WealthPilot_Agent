"""LLM adapter. Business code depends only on LangChain's BaseChatModel interface, never on a
vendor SDK directly.

Providers (LLM_PROVIDER):
- openai_compatible (default; "openai" is an alias): any OpenAI-compatible endpoint, e.g. Kimi,
  OpenAI, DeepSeek, Qwen (DashScope compatible mode), Zhipu GLM, Groq, OpenRouter, Ollama, vLLM.
  Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.
- anthropic: Claude through the native API (LLM_BASE_URL is not used).
- gemini: Google Gemini through the native API (LLM_BASE_URL is not used).
- azure_openai: Azure OpenAI. LLM_BASE_URL is the resource endpoint, LLM_MODEL the deployment name,
  LLM_API_VERSION the API version.
- fake: canned replies for load testing (see app/llm/fake.py; wired in app/api/chat.py).

Only Kimi has been evaluated end to end. Switching providers is a config change, but re-run
evaluations/run_scenarios.py before trusting a new model.
"""

from urllib.parse import urlparse

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableLambda

from app.core.config import Settings, get_settings

PROVIDERS = ("openai_compatible", "anthropic", "gemini", "azure_openai")
ALIASES = {"openai": "openai_compatible"}

# Kimi (Moonshot) API rules: thinking mode only accepts temperature=1 and non-thinking only 0.6;
# thinking is turned off with a vendor-specific request field. Applied only to Moonshot endpoints,
# because other OpenAI-compatible providers reject the unknown field.
KIMI_TEMPERATURE_THINKING = 1.0
KIMI_TEMPERATURE = 0.6
KIMI_NO_THINKING_BODY = {"thinking": {"type": "disabled"}}

# Claude requires max_tokens; enough for the longest replies the agent writes
ANTHROPIC_DEFAULT_MAX_TOKENS = 4096

SYSTEM_NOTE_PREFIX = "[System instruction]"


class LLMNotConfiguredError(RuntimeError):
    pass


def provider_name(settings: Settings) -> str:
    name = settings.llm_provider.strip().lower()
    return ALIASES.get(name, name)


def is_kimi(settings: Settings) -> bool:
    host = urlparse(settings.llm_base_url).hostname or ""
    return provider_name(settings) == "openai_compatible" and "moonshot" in host


def get_chat_model(
    settings: Settings | None = None,
    *,
    thinking: bool | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> BaseChatModel:
    """Build the chat model for the configured provider.

    thinking=None uses the main-agent setting from config. Thinking is a Kimi and Gemini switch; for
    other providers, pick a reasoning or non-reasoning model by name instead. Simple classification
    such as topic routing should run without thinking.
    model overrides LLM_MODEL (used for LLM_ROUTER_MODEL).
    """
    settings = settings or get_settings()
    provider = provider_name(settings)
    if provider not in PROVIDERS:
        raise LLMNotConfiguredError(
            f"未知的 LLM_PROVIDER={settings.llm_provider}，可选：{', '.join(PROVIDERS)}"
        )
    if not settings.llm_api_key.get_secret_value():
        raise LLMNotConfiguredError("未配置 LLM_API_KEY，请在仓库根目录 .env 中填写")
    if thinking is None:
        thinking = settings.llm_agent_thinking
    name = model or settings.llm_model
    common = {
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }

    if provider == "openai_compatible":
        from langchain_openai import ChatOpenAI

        extra_body = None
        if is_kimi(settings):
            common["temperature"] = KIMI_TEMPERATURE_THINKING if thinking else KIMI_TEMPERATURE
            extra_body = None if thinking else KIMI_NO_THINKING_BODY
        return ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=name,
            max_tokens=max_tokens,
            extra_body=extra_body,
            **common,
        )

    if provider == "azure_openai":
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            azure_deployment=name,
            api_version=settings.llm_api_version,
            max_tokens=max_tokens,
            **common,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        inner = ChatAnthropic(
            model=name,
            api_key=settings.llm_api_key,
            max_tokens=max_tokens or ANTHROPIC_DEFAULT_MAX_TOKENS,
            **common,
        )
        return SystemFirstChatModel(inner=inner)

    from langchain_google_genai import ChatGoogleGenerativeAI

    gemini_kwargs = {} if thinking else {"thinking_budget": 0}
    inner = ChatGoogleGenerativeAI(
        model=name,
        api_key=settings.llm_api_key,
        max_tokens=max_tokens,
        **common,
        **gemini_kwargs,
    )
    return SystemFirstChatModel(inner=inner)


def get_router_model(settings: Settings | None = None, *, max_tokens: int) -> BaseChatModel:
    """Model for topic routing: LLM_ROUTER_MODEL if set (e.g. a cheaper model), thinking off."""
    settings = settings or get_settings()
    return get_chat_model(
        settings, thinking=False, max_tokens=max_tokens, model=settings.llm_router_model or None
    )


# ---------- Providers that accept system instructions only at the start ----------


def system_first(messages: list[BaseMessage] | PromptValue) -> list[BaseMessage]:
    """Rewrite a conversation for providers that allow system instructions only at the start.

    The agent adds system messages mid-conversation (rewrite feedback after a failed review, the
    tool-limit instruction). Claude rejects them, and Gemini silently moves them into the leading
    system instruction, so the model would never see the feedback where it belongs. Leading system
    messages are merged; later ones become user messages marked as system instructions, merged into
    a preceding user message so roles still alternate.
    """
    if isinstance(messages, PromptValue):
        messages = messages.to_messages()
    leading: list[str] = []
    i = 0
    while i < len(messages) and isinstance(messages[i], SystemMessage):
        leading.append(_text(messages[i]))
        i += 1
    out: list[BaseMessage] = [SystemMessage("\n\n".join(leading))] if leading else []
    for message in messages[i:]:
        if not isinstance(message, SystemMessage):
            out.append(message)
            continue
        note = f"{SYSTEM_NOTE_PREFIX}\n{_text(message)}"
        last = out[-1] if out else None
        if isinstance(last, HumanMessage) and isinstance(last.content, str):
            out[-1] = HumanMessage(f"{last.content}\n\n{note}")
        else:
            out.append(HumanMessage(note))
    return out


def _text(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(p.get("text", "") for p in message.content if isinstance(p, dict))


class SystemFirstChatModel(BaseChatModel):
    """Wraps a provider model so every request goes through system_first().

    Business code keeps using the BaseChatModel interface (invoke, bind_tools) unchanged.
    """

    inner: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return self.inner._llm_type

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return self.inner._generate(
            system_first(messages), stop=stop, run_manager=run_manager, **kwargs
        )

    def bind_tools(self, tools, **kwargs):
        return RunnableLambda(system_first) | self.inner.bind_tools(tools, **kwargs)
