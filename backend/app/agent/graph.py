"""Main LangGraph flow.

    START → scope_router ─┬─ OUT_OF_SCOPE ─────────────────→ out_of_scope ───────┐
                          ├─ product, not assessed ────────→ assessment_required ┤
                          └─ other → agent ⇄ tools → output_guard ─(fail)→ agent │
                                                       └─(pass)───────────────→ finalize → END

Permissions (permission / risk_rating) are computed by the API layer from the database and passed
in; the graph only reads them.
Three compliance layers: (1) tools bound by permission (agent), (2) re-checked before execution
(tools), (3) output review (output_guard).
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
# Process results (handoff, assessment entry, recorded needs) state no facts, so they don't need the
# "general information" label
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
    # base profile + current needs, rebuilt by the API layer for every message
    customer_context: str
    permission: Permission
    risk_rating: str | None
    gate_reasons: list[str]
    intent: str
    reply: str
    ui_blocks: list[dict]
    guard_attempts: int
    # turn deadline (time.monotonic), set by the API layer from chat_turn_budget_seconds
    deadline: float
    timed_out: bool
    policy_decisions: Annotated[list[dict], operator.add]


def current_turn(messages: list[BaseMessage]) -> list[BaseMessage]:
    """All messages after the latest user message, i.e. the ones produced in this turn."""
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
            # Over the turn time budget: stop calling the model; tool results already produced
            # (product lists, calculations) are still shown
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
        """Second layer: even if the model calls a tool that isn't bound, it is blocked by
        permission before execution."""
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
            # Pass the full state: product tools read the customer's rating via InjectedState
            # (invisible to the LLM)
            # Pass this turn's messages (the last one is the pending call) so tools can limit
            # repeated calls within the turn
            result = tool_node.invoke(
                {**state, "messages": [*state["messages"][:-1], permitted]}, config
            )
            messages = result["messages"] + messages
        decisions = [_decision("TOOL", "BLOCK_TOOL", [f"TOOL:{c['name']}"]) for c in blocked]
        return {"messages": messages, "policy_decisions": decisions}

    def tool_limit(state: AgentState):
        """Tool-call limit reached: run no more tools and let the model answer from existing results
        (no tools bound).

        UI blocks already produced are still shown; the summary still goes through output review,
        and the fixed reply is used only if it fails or is empty.
        """
        prompt = system_prompt(
            state["permission"], state.get("risk_rating"), state.get("customer_context", "")
        )
        # Drop the unexecuted tool-call message so the model API doesn't require matching tool
        # results
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
        """Third layer: on the first failure the model rewrites once; on a second failure a safe
        fallback reply is used."""
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
            # Steering sentences survive the rewrite: remove them and keep the rest if it passes
            # re-review, instead of falling back entirely
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
        # Disclaimers and assessment reminders are appended by code instead of relying on the LLM to
        # remember them
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
        # The model may call the same tool repeatedly; drop identical blocks from the UI
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
    """Uniform handling of tool exceptions (found during P8-4 fault injection).

    By default LangGraph only handles argument validation errors; any other exception inside a tool
    (e.g. the vector store is down) fails the whole turn.
    Here the full exception is logged (with the request ID) and the model gets one sentence with no
    internal details, so it can still answer;
    the ToolMessage status is error and counts as a tool failure in metrics. Expected business
    errors (ToolException) are returned as is.
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
    """When the same turn simulates several allocations, show only one: the last that passed its
    checks, or the last one if none passed.

    The others are drafts before adjustment and would contradict each other side by side; the model
    usually answers with the passing plan (scenario V02).
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
    """Source IDs retrieved this turn: every [ID] in the reply must be among them, otherwise it's
    a fabricated citation."""
    return {i["id"] for b in _source_blocks(current_turn(state["messages"])) for i in b["items"]}


def _label_evidence(blocks: list[dict], reply: str, intent: str | None) -> tuple[list[dict], dict]:
    """Label what the reply is based on: cited sources / retrieved but uncited references / general
    information.

    Also produces the audit record: which sources were cited, in which version.
    """
    cited = set(CITATION_RE.findall(reply))
    labelled, codes, decision = [], [], "GENERAL"
    for b in blocks:
        if b["type"] != "sources":
            labelled.append(b)
            continue
        if not b["confident"] or not b["items"]:
            # nothing found: don't show an empty sources block; the general-information label below
            # applies
            continue
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
    """Content that appeared before the reply, used to check that products mentioned in the reply
    have a source.

    Before an assessment only product names the customer said and existing holdings in the profile
    count; after it, earlier replies and tool results count too.
    """
    earlier = _evidence(state)
    if state["permission"] is Permission.ASSESSMENT_REQUIRED:
        earlier = [m for m in earlier if isinstance(m, HumanMessage)]
    # Customer profile (including holdings in the bank's system): mentioning the customer's own
    # holdings isn't a leak (scenario R01)
    profile = state.get("customer_context", "")
    return "\n".join([profile, *(_text(m) for m in earlier)])


def _facts(state: AgentState) -> str:
    """Basis for checking amounts: customer profile + all earlier messages and tool results
    (regardless of assessment state; calculators work before an assessment)."""
    return "\n".join([state.get("customer_context", ""), *(_text(m) for m in _evidence(state))])


def _evidence(state: AgentState) -> list[BaseMessage]:
    """Earlier messages that may serve as evidence: customer messages, tool results, and final
    replies from earlier turns (all already reviewed).

    Excludes system messages and anything the model wrote in this turn: if a draft rejected by
    review counted as evidence,
    a rewrite could pass by repeating the same made-up amount or product (found in scenario R01,
    2026-10-19).
    History is loaded from the database and holds only reviewed final replies, so unreviewed content
    can only appear in this turn.
    """
    earlier = state["messages"][:-1]
    turn_start = len(earlier) - len(current_turn(earlier))
    return [
        m
        for i, m in enumerate(earlier)
        if not isinstance(m, SystemMessage) and not (i >= turn_start and isinstance(m, AIMessage))
    ]


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
