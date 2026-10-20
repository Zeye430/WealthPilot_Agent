"""Model providers (no network): each provider gets the right parameters, and providers that accept
system instructions only at the start still see rewrite feedback where it belongs."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.agent.graph import build_graph
from app.agent.prompts import SAFE_FALLBACK_REPLY
from app.compliance.policy import Permission
from app.core.config import Settings
from app.llm.client import (
    SYSTEM_NOTE_PREFIX,
    LLMNotConfiguredError,
    SystemFirstChatModel,
    get_chat_model,
    get_router_model,
    system_first,
)
from tests.fakes import ScriptedChatModel, tool_call


def settings(**kw) -> Settings:
    # Ignore the developer's .env so tests don't depend on local settings
    return Settings(_env_file=None, llm_api_key=SecretStr("test-key"), **kw)


OPENAI = {"llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4.1"}

# What the agent actually sends after a failed review: rewrite feedback after the model's draft
REWRITE = [
    SystemMessage("rules"),
    HumanMessage("question"),
    AIMessage("draft"),
    SystemMessage("feedback: rewrite"),
]
# Tool-call limit: the instruction comes after tool results
TOOL_LIMIT = [
    SystemMessage("rules"),
    HumanMessage("question"),
    tool_call("calculate_growth", {"principal": 1}),
    ToolMessage('{"final_value": "1.05"}', tool_call_id="call_1"),
    SystemMessage("answer from existing results"),
]


# ---------- Kimi and other OpenAI-compatible endpoints ----------


def test_kimi_keeps_its_api_rules():
    model = get_chat_model(settings(llm_temperature=0.2))  # Kimi ignores the generic temperature
    assert isinstance(model, ChatOpenAI)
    assert model.temperature == 0.6
    assert model.extra_body == {"thinking": {"type": "disabled"}}
    thinking = get_chat_model(settings(), thinking=True)
    assert thinking.temperature == 1.0 and thinking.extra_body is None


def test_other_openai_compatible_gets_no_kimi_fields():
    model = get_chat_model(settings(**OPENAI, llm_temperature=0.2))
    assert model.extra_body is None and model.temperature == 0.2
    # Unset or empty LLM_TEMPERATURE omits it, for models that accept only their default
    assert get_chat_model(settings(**OPENAI)).temperature is None
    assert get_chat_model(settings(**OPENAI, llm_temperature="")).temperature is None
    assert type(get_chat_model(settings(**OPENAI, llm_provider="openai"))) is ChatOpenAI  # alias


def test_router_model_override():
    router = get_router_model(settings(**OPENAI, llm_router_model="gpt-4.1-mini"), max_tokens=16)
    assert router.model_name == "gpt-4.1-mini" and router.max_tokens == 16
    assert get_router_model(settings(**OPENAI), max_tokens=16).model_name == "gpt-4.1"


def test_azure_openai():
    model = get_chat_model(
        settings(
            llm_provider="azure_openai",
            llm_base_url="https://example.openai.azure.com",
            llm_model="wealthpilot-gpt",
        )
    )
    assert model.deployment_name == "wealthpilot-gpt"
    assert model.azure_endpoint == "https://example.openai.azure.com"


def test_misconfiguration_is_reported():
    with pytest.raises(LLMNotConfiguredError):
        get_chat_model(settings(llm_provider="bogus"))
    with pytest.raises(LLMNotConfiguredError):
        get_chat_model(Settings(_env_file=None, llm_api_key=SecretStr("")))


# ---------- Providers that accept system instructions only at the start ----------


def test_system_first_moves_mid_conversation_instructions_into_user_turns():
    out = system_first(REWRITE)
    assert [type(m).__name__ for m in out] == [
        "SystemMessage",
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]
    assert out[0].content == "rules"
    assert out[-1].content == f"{SYSTEM_NOTE_PREFIX}\nfeedback: rewrite"
    # A note right after a user message is merged into it, so roles still alternate
    merged = system_first(
        [SystemMessage("a"), SystemMessage("b"), HumanMessage("q"), SystemMessage("n")]
    )
    assert merged[0].content == "a\n\nb"
    assert len(merged) == 2 and merged[1].content == f"q\n\n{SYSTEM_NOTE_PREFIX}\nn"


def test_claude_request_keeps_feedback_in_place():
    model = get_chat_model(settings(llm_provider="anthropic", llm_model="claude-sonnet-5-5"))
    assert isinstance(model, SystemFirstChatModel)
    assert model.inner.temperature is None  # newer Claude models reject non-default temperatures
    with pytest.raises(ValueError):  # what would happen without the wrapper
        model.inner._get_request_payload(REWRITE)
    payload = model.inner._get_request_payload(system_first(REWRITE))
    assert payload["system"] == "rules" or payload["system"][0]["text"] == "rules"
    assert payload["messages"][-1]["role"] == "user"
    assert SYSTEM_NOTE_PREFIX in str(payload["messages"][-1]["content"])
    tools = model.inner._get_request_payload(system_first(TOOL_LIMIT))
    assert tools["messages"][-1]["role"] == "user"


def test_gemini_request_keeps_feedback_in_place():
    model = get_chat_model(settings(llm_provider="gemini", llm_model="gemini-2.5-flash"))
    assert isinstance(model, SystemFirstChatModel)
    assert model.inner.thinking_budget == 0  # thinking off, so short router outputs aren't used up
    # Without the wrapper, Gemini silently moves the feedback into the system instruction
    raw = model.inner._prepare_request(REWRITE)
    assert [p.text for p in raw["config"].system_instruction.parts] == [
        "rules",
        "feedback: rewrite",
    ]
    request = model.inner._prepare_request(system_first(REWRITE))
    assert [p.text for p in request["config"].system_instruction.parts] == ["rules"]
    last = request["contents"][-1]
    assert last.role == "user" and SYSTEM_NOTE_PREFIX in last.parts[0].text


def test_agent_flow_through_the_wrapper():
    """The rewrite loop works unchanged on a wrapped model, and the model never sees a mid-run
    system message."""
    inner = ScriptedChatModel(responses=[AIMessage("稳赚不赔。"), AIMessage("保证收益。")])
    router = ScriptedChatModel(responses=[AIMessage("FINANCE_KNOWLEDGE")])
    graph = build_graph(SystemFirstChatModel(inner=inner), SystemFirstChatModel(inner=router))
    result = graph.invoke(
        {
            "messages": [HumanMessage("这个稳吗？")],
            "permission": Permission.ASSESSED,
            "risk_rating": "C2",
            "gate_reasons": [],
            "policy_decisions": [],
        }
    )
    assert result["reply"] == SAFE_FALLBACK_REPLY  # review still rejects both drafts
    rewrite_call = inner.received[1]
    assert not any(isinstance(m, SystemMessage) for m in rewrite_call[1:])
    assert SYSTEM_NOTE_PREFIX in rewrite_call[-1].content
