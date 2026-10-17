"""LangGraph 主流程（Phase 1：agent ↔ tools 循环 + finalize）。

Phase 2 会在 agent 之前插入 load_context / policy_gate / scope_router，见 docs/ARCHITECTURE.md §4。
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.prompts import SYSTEM_PROMPT
from app.tools.calculation_tools import CALCULATION_TOOLS, HYPOTHETICAL_NOTE

TOOL_LIMIT_REPLY = (
    "这个问题需要的计算步骤较多，我先停在这里。您可以把问题拆小一些，或联系理财经理协助。"
)


class AgentState(MessagesState):
    reply: str
    ui_blocks: list[dict]


def current_turn(messages: list[BaseMessage]) -> list[BaseMessage]:
    """最近一条用户消息之后的所有消息，即本轮产生的消息。"""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i + 1 :]
    return messages


def build_graph(model: BaseChatModel, max_tool_calls: int = 6):
    tools = CALCULATION_TOOLS
    model_with_tools = model.bind_tools(tools)

    def agent(state: AgentState):
        response = model_with_tools.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return "finalize"
        used = sum(isinstance(m, ToolMessage) for m in current_turn(state["messages"]))
        if used + len(last.tool_calls) > max_tool_calls:
            return "tool_limit"
        return "tools"

    def tool_limit(state: AgentState):
        return {"reply": TOOL_LIMIT_REPLY, "ui_blocks": []}

    def finalize(state: AgentState):
        turn = current_turn(state["messages"])
        blocks: list[dict] = []
        for m in turn:
            if isinstance(m, ToolMessage) and m.status == "success" and m.artifact:
                blocks.extend(m.artifact)
        reply = state.get("reply") or _text(state["messages"][-1])
        # 免责声明由代码追加，而不是依赖 LLM 自己记得写
        if blocks and HYPOTHETICAL_NOTE not in reply:
            reply = f"{reply}\n\n> {HYPOTHETICAL_NOTE}"
        return {"reply": reply, "ui_blocks": blocks}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("tool_limit", tool_limit)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, ["tools", "tool_limit", "finalize"])
    graph.add_edge("tools", "agent")
    graph.add_edge("tool_limit", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
