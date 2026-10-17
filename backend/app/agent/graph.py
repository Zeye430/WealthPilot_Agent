"""LangGraph 主流程，见 docs/ARCHITECTURE.md §4。

    START → scope_router ─┬─ OUT_OF_SCOPE ─────────────────→ out_of_scope ───────┐
                          ├─ 要产品但未测评 ───────────────→ assessment_required ┤
                          └─ 其他 → agent ⇄ tools → output_guard ─(未通过)→ agent │
                                                       └─(通过)───────────────→ finalize → END

权限（permission / risk_rating）由 API 层从数据库算出后传入，图内只读。
合规三道防线：①按权限绑定工具（agent）②工具执行前再校验（tools）③输出审查（output_guard）。
"""

import json
import operator
import re
from typing import Annotated

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent import router
from app.agent.prompts import (
    ASSESSMENT_REQUIRED_REPLY,
    OUT_OF_SCOPE_REPLY,
    SAFE_FALLBACK_REPLY,
    TOOL_LIMIT_REPLY,
    system_prompt,
)
from app.compliance import output_guard
from app.compliance.policy import RULE_VERSION, Permission, tool_allowed
from app.tools.assessment_tools import ASSESSMENT_PROMPT_BLOCK, ASSESSMENT_TOOLS
from app.tools.calculation_tools import CALCULATION_TOOLS, HYPOTHETICAL_NOTE
from app.tools.document_tools import DOCUMENT_TOOLS
from app.tools.product_tools import PRODUCT_TOOLS
from app.tools.profile_tools import PROFILE_TOOLS

ALL_TOOLS = [*ASSESSMENT_TOOLS, *CALCULATION_TOOLS, *PRODUCT_TOOLS, *DOCUMENT_TOOLS, *PROFILE_TOOLS]
REMINDER_BLOCK = {**ASSESSMENT_PROMPT_BLOCK, "variant": "reminder"}
CALCULATION_BLOCK_TYPES = {"calculation_result", "line_chart"}
EVIDENCE_BLOCK_TYPES = {
    "calculation_result",
    "product_list",
    "product_detail",
    "comparison_table",
    "allocation",
}
GENERAL_NOTE = {"type": "source_note", "variant": "general", "text": "一般性说明，未引用资料"}
CITATION_RE = re.compile(r"\[(K\d{2}|[A-Z]{2}-[A-Z]\d{2}#[^\]\s]+)\]")


class AgentState(MessagesState):
    customer_id: str
    customer_context: str  # 基础画像 + 本次需求，由 API 层每条消息重新组装
    permission: Permission
    risk_rating: str | None
    gate_reasons: list[str]
    intent: str
    reply: str
    ui_blocks: list[dict]
    guard_attempts: int
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


def build_graph(model: BaseChatModel, router_model: BaseChatModel, max_tool_calls: int = 6):
    pre_tools = [t for t in ALL_TOOLS if tool_allowed(Permission.ASSESSMENT_REQUIRED, t.name)]
    bound = {
        Permission.ASSESSMENT_REQUIRED: model.bind_tools(pre_tools),
        Permission.ASSESSED: model.bind_tools(ALL_TOOLS),
    }
    tool_node = ToolNode(ALL_TOOLS)

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
        return {"reply": OUT_OF_SCOPE_REPLY}

    def assessment_required(state: AgentState):
        return {
            "reply": ASSESSMENT_REQUIRED_REPLY,
            "ui_blocks": [ASSESSMENT_PROMPT_BLOCK],
            "policy_decisions": [
                _decision("GATE", "BLOCK_PRODUCT_REQUEST", state.get("gate_reasons"))
            ],
        }

    def agent(state: AgentState):
        prompt = system_prompt(
            state["permission"], state.get("risk_rating"), state.get("customer_context", "")
        )
        response = bound[state["permission"]].invoke([SystemMessage(prompt), *state["messages"]])
        return {"messages": [response]}

    def route_after_agent(state: AgentState) -> str:
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
            result = tool_node.invoke({**state, "messages": [permitted]}, config)
            messages = result["messages"] + messages
        decisions = [_decision("TOOL", "BLOCK_TOOL", [f"TOOL:{c['name']}"]) for c in blocked]
        return {"messages": messages, "policy_decisions": decisions}

    def tool_limit(state: AgentState):
        return {"reply": TOOL_LIMIT_REPLY}

    def guard(state: AgentState):
        """第三道防线：首次未通过让模型改写一次，再次未通过使用安全兜底回答。"""
        reply = _text(state["messages"][-1])
        violations = output_guard.check_output(
            reply, state["permission"], _grounding(state), _retrieved_ids(state)
        )
        if not violations:
            return {}
        attempts = state.get("guard_attempts", 0)
        if attempts == 0:
            return {
                "guard_attempts": 1,
                "messages": [SystemMessage(output_guard.describe(violations, reply))],
                "policy_decisions": [_decision("OUTPUT", "REWRITE", violations)],
            }
        return {
            "reply": SAFE_FALLBACK_REPLY,
            "policy_decisions": [_decision("OUTPUT", "FALLBACK", violations)],
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
        if has_calculation and HYPOTHETICAL_NOTE not in reply:
            reply = f"{reply}\n\n> {HYPOTHETICAL_NOTE}"
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
            blocks.append(REMINDER_BLOCK)
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
    graph.add_conditional_edges("agent", route_after_agent, ["tools", "tool_limit", "output_guard"])
    graph.add_edge("tools", "agent")
    graph.add_edge("tool_limit", "finalize")
    graph.add_conditional_edges("output_guard", route_after_guard, ["agent", "finalize"])
    graph.add_edge("finalize", END)
    return graph.compile()


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
    if not has_evidence and intent in (router.FINANCE_KNOWLEDGE, router.PRODUCT_OR_ADVICE):
        labelled.append(GENERAL_NOTE)
    if not codes and has_evidence:
        decision = "TOOL_DATA"
    return labelled, _decision("EVIDENCE", decision, codes)


def _grounding(state: AgentState) -> str:
    """回答之前已出现的内容，用于核对回答提到的产品是否有来源。

    测评前只认客户自己说过的产品名；测评后还包括历史回答和工具结果。
    """
    earlier = state["messages"][:-1]
    if state["permission"] is Permission.ASSESSMENT_REQUIRED:
        earlier = [m for m in earlier if isinstance(m, HumanMessage)]
    return "\n".join(_text(m) for m in earlier if not isinstance(m, SystemMessage))


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
