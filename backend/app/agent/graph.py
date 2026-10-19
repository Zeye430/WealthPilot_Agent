"""LangGraph 主流程，见 docs/ARCHITECTURE.md §4。

    START → scope_router ─┬─ OUT_OF_SCOPE ─────────────────→ out_of_scope ───────┐
                          ├─ 要产品但未测评 ───────────────→ assessment_required ┤
                          └─ 其他 → agent ⇄ tools → output_guard ─(未通过)→ agent │
                                                       └─(通过)───────────────→ finalize → END

权限（permission / risk_rating）由 API 层从数据库算出后传入，图内只读。
合规三道防线：①按权限绑定工具（agent）②工具执行前再校验（tools）③输出审查（output_guard）。
"""

import json
import logging
import operator
import re
import time
from collections.abc import Callable
from typing import Annotated

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import ToolException
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent import router
from app.agent.prompts import (
    ASSESSMENT_REQUIRED_REPLY,
    OUT_OF_SCOPE_REPLY,
    SAFE_FALLBACK_REPLY,
    TOOL_LIMIT_INSTRUCTION,
    TOOL_LIMIT_REPLY,
    TURN_TIMEOUT_REPLY,
    system_prompt,
)
from app.compliance import output_guard
from app.compliance.policy import RULE_VERSION, Permission, tool_allowed
from app.core.i18n import L, localized
from app.tools.assessment_tools import ASSESSMENT_TOOLS, assessment_prompt_block
from app.tools.benefit_tools import BENEFIT_TOOLS
from app.tools.calculation_tools import CALCULATION_TOOLS, HYPOTHETICAL_NOTE
from app.tools.document_tools import DOCUMENT_TOOLS
from app.tools.handoff_tools import HANDOFF_TOOLS
from app.tools.product_tools import PRODUCT_TOOLS
from app.tools.profile_tools import PROFILE_TOOLS

ALL_TOOLS = [
    *ASSESSMENT_TOOLS,
    *CALCULATION_TOOLS,
    *PRODUCT_TOOLS,
    *BENEFIT_TOOLS,
    *DOCUMENT_TOOLS,
    *PROFILE_TOOLS,
    *HANDOFF_TOOLS,
]
CALCULATION_BLOCK_TYPES = {"calculation_result", "line_chart"}
EVIDENCE_BLOCK_TYPES = {
    "calculation_result",
    "product_list",
    "product_detail",
    "comparison_table",
    "allocation",
}
# 流程性结果（转人工、测评入口、记录需求）不含事实陈述，不需要标注「一般性说明」
PROCEDURAL_BLOCK_TYPES = {"rm_contact", "assessment_prompt", "needs_update"}


def general_note() -> dict:
    return {
        "type": "source_note",
        "variant": "general",
        "text": L("一般性说明，未引用资料", "General information, no source cited"),
    }


logger = logging.getLogger(__name__)

CITATION_RE = re.compile(r"\[(K\d{2}|[A-Z]{2}-[A-Z]\d{2}#[^\]\s]+)\]")


class AgentState(MessagesState):
    customer_id: str
    conversation_id: str
    customer_context: str  # 基础画像 + 本次需求，由 API 层每条消息重新组装
    permission: Permission
    risk_rating: str | None
    gate_reasons: list[str]
    intent: str
    reply: str
    ui_blocks: list[dict]
    guard_attempts: int
    deadline: float  # 单轮截止时间（time.monotonic），由 API 层按 chat_turn_budget_seconds 设置
    timed_out: bool
    policy_decisions: Annotated[list[dict], operator.add]


def current_turn(messages: list[BaseMessage]) -> list[BaseMessage]:
    """最近一条用户消息之后的所有消息，即本轮产生的消息。"""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i + 1 :]
    return messages


def _decision(checkpoint: str, decision: str, reason_codes: list[str] | None = None) -> dict:
    return {
        "checkpoint": checkpoint,
        "decision": decision,
        "reason_codes": reason_codes or [],
        "rule_version": RULE_VERSION,
    }


def build_graph(
    model: BaseChatModel,
    router_model: BaseChatModel,
    max_tool_calls: int = 6,
    clock: Callable[[], float] = time.monotonic,
):
    pre_tools = [t for t in ALL_TOOLS if tool_allowed(Permission.ASSESSMENT_REQUIRED, t.name)]
    bound = {
        Permission.ASSESSMENT_REQUIRED: model.bind_tools(pre_tools),
        Permission.ASSESSED: model.bind_tools(ALL_TOOLS),
    }
    tool_node = ToolNode(ALL_TOOLS, handle_tool_errors=_tool_error_message)

    def scope_router(state: AgentState):
        intent = router.classify(router_model, state["messages"])
        return {"intent": intent, "policy_decisions": [_decision("ROUTER", intent)]}

    def route_after_router(state: AgentState) -> str:
        if state["intent"] == router.OUT_OF_SCOPE:
            return "out_of_scope"
        if (
            state["intent"] == router.PRODUCT_OR_ADVICE
            and state["permission"] is Permission.ASSESSMENT_REQUIRED
        ):
            return "assessment_required"
        return "agent"

    def out_of_scope(state: AgentState):
        return {"reply": localized(OUT_OF_SCOPE_REPLY)}

    def assessment_required(state: AgentState):
        return {
            "reply": localized(ASSESSMENT_REQUIRED_REPLY),
            "ui_blocks": [assessment_prompt_block()],
            "policy_decisions": [
                _decision("GATE", "BLOCK_PRODUCT_REQUEST", state.get("gate_reasons"))
            ],
        }

    def agent(state: AgentState):
        deadline = state.get("deadline")
        if deadline is not None and clock() > deadline:
            # 超过单轮时长上限：不再调用模型；已执行的工具结果（产品列表、测算等）照常展示
            return {
                "timed_out": True,
                "reply": localized(TURN_TIMEOUT_REPLY),
                "policy_decisions": [_decision("TURN", "TIMEOUT")],
            }
        prompt = system_prompt(
            state["permission"], state.get("risk_rating"), state.get("customer_context", "")
        )
        response = bound[state["permission"]].invoke([SystemMessage(prompt), *state["messages"]])
        return {"messages": [response]}

    def route_after_agent(state: AgentState) -> str:
        if state.get("timed_out"):
            return "finalize"
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return "output_guard"
        used = sum(isinstance(m, ToolMessage) for m in current_turn(state["messages"]))
        if used + len(last.tool_calls) > max_tool_calls:
            return "tool_limit"
        return "tools"

    def tools(state: AgentState, config: RunnableConfig):
        """第二道防线：即使模型调用了未绑定的工具，执行前也会按权限拦截。"""
        last: AIMessage = state["messages"][-1]
        allowed = [c for c in last.tool_calls if tool_allowed(state["permission"], c["name"])]
        blocked = [c for c in last.tool_calls if c not in allowed]
        messages: list[BaseMessage] = [
            ToolMessage(
                content="该工具需要客户完成风险测评后才能使用。",
                tool_call_id=c["id"],
                name=c["name"],
                status="error",
            )
            for c in blocked
        ]
        if allowed:
            permitted = last.model_copy(update={"tool_calls": allowed})
            # 传入完整状态：产品工具通过 InjectedState 读取客户评级（LLM 不可见）
            # 传入本轮完整消息（最后一条为待执行的调用），工具可据此限制本轮的重复调用
            result = tool_node.invoke(
                {**state, "messages": [*state["messages"][:-1], permitted]}, config
            )
            messages = result["messages"] + messages
        decisions = [_decision("TOOL", "BLOCK_TOOL", [f"TOOL:{c['name']}"]) for c in blocked]
        return {"messages": messages, "policy_decisions": decisions}

    def tool_limit(state: AgentState):
        """工具调用达到上限：不再执行工具，让模型根据已有结果作答（不绑定工具）。

        已产生的界面块照常展示；总结仍需通过输出审查，未通过或为空时才用固定话术。
        """
        prompt = system_prompt(
            state["permission"], state.get("risk_rating"), state.get("customer_context", "")
        )
        # 去掉未执行的工具调用消息，避免模型接口要求补齐工具结果
        earlier = state["messages"][:-1]
        summary = model.invoke(
            [SystemMessage(prompt), *earlier, SystemMessage(TOOL_LIMIT_INSTRUCTION)]
        )
        text = _text(summary)
        violations = output_guard.check_output(
            text,
            state["permission"],
            _grounding(state),
            _retrieved_ids(state),
            state.get("risk_rating"),
            facts=_facts(state),
        )
        if getattr(summary, "tool_calls", None) or not text or violations:
            return {
                "reply": localized(TOOL_LIMIT_REPLY),
                "policy_decisions": [_decision("TOOL", "TOOL_LIMIT", violations)],
            }
        return {"reply": text, "policy_decisions": [_decision("TOOL", "TOOL_LIMIT_SUMMARY")]}

    def guard(state: AgentState):
        """第三道防线：首次未通过让模型改写一次，再次未通过使用安全兜底回答。"""
        reply = _text(state["messages"][-1])
        rating = state.get("risk_rating")

        def check(text: str) -> list[str]:
            return output_guard.check_output(
                text,
                state["permission"],
                _grounding(state),
                _retrieved_ids(state),
                rating,
                facts=_facts(state),
            )

        violations = check(reply)
        if not violations:
            return {}
        grounding = _grounding(state)
        snippets = [f"片段:{x}" for x in output_guard.offending_snippets(reply, rating, grounding)]
        if state.get("guard_attempts", 0) == 0:
            return {
                "guard_attempts": 1,
                "messages": [
                    SystemMessage(
                        output_guard.describe(violations, reply, rating, grounding, _facts(state))
                    )
                ],
                "policy_decisions": [_decision("OUTPUT", "REWRITE", [*violations, *snippets])],
            }
        if violations == ["O-REASSESSMENT_STEERING"]:
            # 改写后仍有诱导句：删去这些句子，其余内容通过复查则保留，避免整条回答退化为兜底
            redacted = output_guard.remove_steering(reply)
            if redacted and not check(redacted):
                return {
                    "reply": redacted,
                    "policy_decisions": [_decision("OUTPUT", "REDACT", [*violations, *snippets])],
                }
        return {
            "reply": localized(SAFE_FALLBACK_REPLY),
            "policy_decisions": [_decision("OUTPUT", "FALLBACK", [*violations, *snippets])],
        }

    def route_after_guard(state: AgentState) -> str:
        return "agent" if isinstance(state["messages"][-1], SystemMessage) else "finalize"

    def finalize(state: AgentState):
        blocks = list(state.get("ui_blocks") or [])
        for m in current_turn(state["messages"]):
            if isinstance(m, ToolMessage) and m.status == "success" and m.artifact:
                blocks.extend(m.artifact)
        reply = state.get("reply") or _text(state["messages"][-1])
        # 免责声明和测评提醒由代码追加，而不是依赖 LLM 自己记得写
        has_calculation = any(b["type"] in CALCULATION_BLOCK_TYPES for b in blocks)
        if has_calculation and localized(HYPOTHETICAL_NOTE) not in reply:
            reply = f"{reply}\n\n> {localized(HYPOTHETICAL_NOTE)}"
        question = next(
            (_text(m) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        if state.get("intent") != router.OUT_OF_SCOPE and output_guard.needs_no_guarantee_note(
            question, reply
        ):
            reply = f"{reply}\n\n> {localized(output_guard.NO_GUARANTEE_NOTE)}"
        blocks = latest_allocation_only(blocks)
        # 模型可能重复调用同一工具，界面上去掉内容完全相同的块
        blocks = list(
            {json.dumps(b, sort_keys=True, ensure_ascii=False): b for b in blocks}.values()
        )
        blocks, evidence = _label_evidence(blocks, reply, state.get("intent"))
        needs_reminder = (
            state["permission"] is Permission.ASSESSMENT_REQUIRED
            and state.get("intent") != router.OUT_OF_SCOPE
            and not any(b["type"] == "assessment_prompt" for b in blocks)
        )
        if needs_reminder:
            blocks.append(assessment_prompt_block("reminder"))
        return {"reply": reply, "ui_blocks": blocks, "policy_decisions": [evidence]}

    graph = StateGraph(AgentState)
    graph.add_node("scope_router", scope_router)
    graph.add_node("out_of_scope", out_of_scope)
    graph.add_node("assessment_required", assessment_required)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_node("tool_limit", tool_limit)
    graph.add_node("output_guard", guard)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "scope_router")
    graph.add_conditional_edges(
        "scope_router", route_after_router, ["out_of_scope", "assessment_required", "agent"]
    )
    graph.add_edge("out_of_scope", "finalize")
    graph.add_edge("assessment_required", "finalize")
    graph.add_conditional_edges(
        "agent", route_after_agent, ["tools", "tool_limit", "output_guard", "finalize"]
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("tool_limit", "finalize")
    graph.add_conditional_edges("output_guard", route_after_guard, ["agent", "finalize"])
    graph.add_edge("finalize", END)
    return graph.compile()


def _tool_error_message(error: Exception) -> str:
    """工具执行异常的统一处理（P8-4 故障注入发现）。

    LangGraph 默认只处理参数校验错误，工具内部的其他异常（如向量库不可用）会让整轮对话失败。
    这里记录完整异常（带请求编号），只给模型一句不含内部细节的说明，由模型照常作答；
    ToolMessage 状态为 error，运行指标中计为工具失败。业务上预期的错误（ToolException）原样返回。
    """
    if isinstance(error, ToolException):
        return str(error)
    logger.error("tool failed: %s", type(error).__name__, exc_info=error)
    return L(
        "该工具暂时不可用，请不要编造这部分信息，可如实告知客户稍后再试或联系理财经理。",
        "This tool is temporarily unavailable. Do not make up this information; tell the "
        "customer to try again later or contact their relationship manager.",
    )


def latest_allocation_only(blocks: list[dict]) -> list[dict]:
    """同一轮多次模拟配置时只展示一份：最后一次通过检查的；都没通过则展示最后一次。

    其余是调整前的草稿，并列展示会互相矛盾；模型通常也按通过检查的方案作答（场景评估 V02）。
    """
    allocations = [i for i, b in enumerate(blocks) if b["type"] == "allocation"]
    if len(allocations) <= 1:
        return blocks
    passed = [i for i in allocations if blocks[i].get("passed")]
    keep = (passed or allocations)[-1]
    return [b for i, b in enumerate(blocks) if b["type"] != "allocation" or i == keep]


def _source_blocks(messages: list[BaseMessage]) -> list[dict]:
    return [
        b
        for m in messages
        if isinstance(m, ToolMessage) and m.status == "success" and m.artifact
        for b in m.artifact
        if b["type"] == "sources"
    ]


def _retrieved_ids(state: AgentState) -> set[str]:
    """本轮检索到的资料编号：回答中的 [编号] 必须在其中，否则视为编造出处。"""
    return {i["id"] for b in _source_blocks(current_turn(state["messages"])) for i in b["items"]}


def _label_evidence(blocks: list[dict], reply: str, intent: str | None) -> tuple[list[dict], dict]:
    """标注回答依据：已引用的资料 / 检索到但未引用的参考资料 / 一般性说明。

    同时生成审计记录：引用了哪些资料的哪个版本。
    """
    cited = set(CITATION_RE.findall(reply))
    labelled, codes, decision = [], [], "GENERAL"
    for b in blocks:
        if b["type"] != "sources":
            labelled.append(b)
            continue
        if not b["confident"] or not b["items"]:
            continue  # 未找到资料：不展示空的出处块，由下方一般性说明标注
        used = [i for i in b["items"] if i["id"] in cited]
        items = used or b["items"]
        labelled.append({**b, "items": items, "cited": bool(used)})
        codes += [f"{i['id']}@{i['version']}" for i in items]
        decision = "CITED" if used else "RETRIEVED_NOT_CITED"
    has_evidence = codes or any(b["type"] in EVIDENCE_BLOCK_TYPES for b in labelled)
    procedural = any(b["type"] in PROCEDURAL_BLOCK_TYPES for b in labelled)
    if (
        not has_evidence
        and not procedural
        and intent in (router.FINANCE_KNOWLEDGE, router.PRODUCT_OR_ADVICE)
    ):
        labelled.append(general_note())
    if not codes and has_evidence:
        decision = "TOOL_DATA"
    return labelled, _decision("EVIDENCE", decision, codes)


def _grounding(state: AgentState) -> str:
    """回答之前已出现的内容，用于核对回答提到的产品是否有来源。

    测评前只认客户自己说过的产品名和客户资料中的已有持仓；测评后还包括历史回答和工具结果。
    """
    earlier = state["messages"][:-1]
    if state["permission"] is Permission.ASSESSMENT_REQUIRED:
        earlier = [m for m in earlier if isinstance(m, HumanMessage)]
    # 客户资料（含银行系统中的已有持仓）：提到客户自己持有的产品不算泄露（场景评估 R01）
    profile = state.get("customer_context", "")
    return "\n".join([profile, *(_text(m) for m in earlier if not isinstance(m, SystemMessage))])


def _facts(state: AgentState) -> str:
    """金额核对的依据：客户资料 + 此前所有消息与工具结果（不分测评状态，测算工具测评前也可用）。"""
    earlier = [m for m in state["messages"][:-1] if not isinstance(m, SystemMessage)]
    return "\n".join([state.get("customer_context", ""), *(_text(m) for m in earlier)])


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
