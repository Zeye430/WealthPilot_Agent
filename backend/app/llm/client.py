"""LLM adapter. Business code depends only on LangChain's BaseChatModel interface, never on a
vendor SDK directly.

Providers (LLM_PROVIDER):
- kimi, deepseek, qwen, glm: presets for Chinese OpenAI-compatible APIs. Only LLM_API_KEY is
  required; base URL and model have defaults, and each vendor's way of turning thinking off is
  applied (see VENDORS).
- openai_compatible (default; "openai" is an alias): any OpenAI-compatible endpoint, e.g. OpenAI,
  Groq, OpenRouter, Ollama, vLLM. Set LLM_BASE_URL and LLM_MODEL. If the URL belongs to one of the
  vendors above, its preset applies too (so the default Moonshot URL behaves as kimi).
- anthropic: Claude through the native API (LLM_BASE_URL is not used).
- gemini: Google Gemini through the native API (LLM_BASE_URL is not used).
- azure_openai: Azure OpenAI. LLM_BASE_URL is the resource endpoint, LLM_MODEL the deployment name,
  LLM_API_VERSION the API version.
- fake: canned replies for load testing (see app/llm/fake.py; wired in app/api/chat.py).

Only Kimi has been evaluated end to end. Switching providers is a config change, but re-run
evaluations/run_scenarios.py before trusting a new model.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableLambda

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Vendor:
    """Quirks of an OpenAI-compatible vendor. Model names and URLs change often: defaults apply only
    when LLM_BASE_URL / LLM_MODEL aren't set, so users can always override them."""

    name: str
    hosts: tuple[str, ...]  # LLM_BASE_URL hosts that identify the vendor
    base_url: str
    model: str
    thinking_off: dict  # request body fields that turn thinking off
    # Fields that turn thinking on; None means thinking can't be used with tool calls here
    thinking_on: dict | None
    # Temperatures fixed by the API for (thinking, no thinking); None uses LLM_TEMPERATURE
    temperature: tuple[float, float] | None = None


# Checked against each vendor's official docs, 2026-10. All think by default in their newer models,
# so thinking is turned off explicitly: it doubles latency and, for routing, would use up the
# 16-token output limit.
VENDORS = {
    "kimi": Vendor(
        name="kimi",
        hosts=("moonshot.ai", "moonshot.cn"),
        base_url="https://api.moonshot.ai/v1",
        model="kimi-k2.6",
        thinking_off={"thinking": {"type": "disabled"}},
        thinking_on={},
        temperature=(1.0, 0.6),  # Kimi accepts only 1 with thinking and 0.6 without
    ),
    "deepseek": Vendor(
        name="deepseek",
        hosts=("deepseek.com",),
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        thinking_off={"thinking": {"type": "disabled"}},
        # In thinking mode DeepSeek requires reasoning_content to be sent back on every later
        # request, which LangChain's OpenAI client doesn't do, so tool-calling turns would fail
        # with a 400
        thinking_on=None,
    ),
    "qwen": Vendor(
        name="qwen",
        hosts=("aliyuncs.com",),
        # Still served, but Alibaba now recommends the workspace URL, e.g.
        # https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",  # tool calling is supported on qwen-plus and qwen-max
        thinking_off={"enable_thinking": False},
        thinking_on={"enable_thinking": True},
    ),
    "glm": Vendor(
        name="glm",
        hosts=("z.ai", "bigmodel.cn"),
        base_url="https://api.z.ai/api/paas/v4",  # China: https://open.bigmodel.cn/api/paas/v4
        model="glm-4.7",  # GLM-5.3 always thinks and can't be switched off
        thinking_off={"thinking": {"type": "disabled"}},
        thinking_on={"thinking": {"type": "enabled"}},
    ),
}

PROVIDERS = ("openai_compatible", *VENDORS, "anthropic", "gemini", "azure_openai")
ALIASES = {"openai": "openai_compatible"}

# Claude requires max_tokens; enough for the longest replies the agent writes
ANTHROPIC_DEFAULT_MAX_TOKENS = 4096

SYSTEM_NOTE_PREFIX = "[System instruction]"


class LLMNotConfiguredError(RuntimeError):
    pass


def provider_name(settings: Settings) -> str:
    name = settings.llm_provider.strip().lower()
    return ALIASES.get(name, name)


def vendor_of(settings: Settings) -> Vendor | None:
    """The vendor preset: named by LLM_PROVIDER, or recognized from an OpenAI-compatible URL."""
    provider = provider_name(settings)
    if provider in VENDORS:
        return VENDORS[provider]
    if provider != "openai_compatible":
        return None
    return _host_vendor(settings.llm_base_url)


def resolved_endpoint(settings: Settings) -> tuple[str, str]:
    """(base URL, model): explicit non-empty settings win, otherwise the vendor preset's."""
    vendor = VENDORS.get(provider_name(settings))
    explicit = settings.model_fields_set
    base_url = settings.llm_base_url.strip()
    model = settings.llm_model.strip()
    if vendor:
        if "llm_base_url" not in explicit or not base_url:
            base_url = vendor.base_url
        if "llm_model" not in explicit or not model:
            model = vendor.model
    return base_url, model


def _host_vendor(base_url: str) -> Vendor | None:
    host = urlparse(base_url).hostname or ""
    for vendor in VENDORS.values():
        if any(host == h or host.endswith("." + h) for h in vendor.hosts):
            return vendor
    return None


def prices_are_defaults(settings: Settings) -> bool:
    """True when cost estimates still use the default (Kimi) prices for a non-Kimi model."""
    explicit = settings.model_fields_set
    kimi = vendor_of(settings) is VENDORS["kimi"]
    unset = not {"llm_price_input_per_mtok", "llm_price_output_per_mtok"} & explicit
    return unset and not kimi and provider_name(settings) != "fake"


def get_chat_model(
    settings: Settings | None = None,
    *,
    thinking: bool | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> BaseChatModel:
    """Build the chat model for the configured provider.

    thinking=None uses the main-agent setting from config. Thinking is a switch for the vendor
    presets and Gemini; for other providers, pick a reasoning or non-reasoning model by name.
    Simple classification such as topic routing should run without thinking.
    model overrides the configured model (used for LLM_ROUTER_MODEL).
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
    base_url, default_model = resolved_endpoint(settings)
    if not base_url and provider in ("openai_compatible", "azure_openai"):
        raise LLMNotConfiguredError(f"LLM_PROVIDER={provider} 需要设置 LLM_BASE_URL")
    if not default_model:
        raise LLMNotConfiguredError("未设置 LLM_MODEL")
    url_vendor = _host_vendor(base_url)
    if provider in VENDORS and url_vendor and url_vendor.name != provider:
        # Usually a leftover URL after switching LLM_PROVIDER: the key would go to the wrong vendor
        raise LLMNotConfiguredError(
            f"LLM_PROVIDER={provider}，但 LLM_BASE_URL 指向 {url_vendor.name}："
            "请清空或修改 LLM_BASE_URL"
        )
    name = model or default_model
    common = {
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }

    if provider == "openai_compatible" or provider in VENDORS:
        from langchain_openai import ChatOpenAI

        extra_body = None
        vendor = vendor_of(settings)
        if vendor:
            if thinking and vendor.thinking_on is None:
                logger.warning(
                    "%s: thinking can't be used with tool calls here; turned off", vendor.name
                )
                thinking = False
            extra_body = (vendor.thinking_on if thinking else vendor.thinking_off) or None
            if vendor.temperature:
                common["temperature"] = vendor.temperature[0 if thinking else 1]
        return ChatOpenAI(
            base_url=base_url,
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


def describe(settings: Settings) -> dict:
    """Provider summary for the readiness check and logs (no secrets)."""
    provider = provider_name(settings)
    vendor = vendor_of(settings)
    _, model = resolved_endpoint(settings)
    info = {"provider": provider, "model": model}
    if vendor and vendor.name != provider:
        info["vendor"] = vendor.name
    if settings.llm_router_model:
        info["router_model"] = settings.llm_router_model
    if prices_are_defaults(settings):
        info["prices"] = "default (Kimi); set LLM_PRICE_*"
    return info


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
