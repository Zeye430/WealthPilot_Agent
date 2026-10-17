from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import TOOL_LIMIT_REPLY, build_graph
from app.tools.calculation_tools import HYPOTHETICAL_NOTE
from tests.fakes import ScriptedChatModel, tool_call


def run(model, text="100万按每年5%复利10年是多少？", max_tool_calls=6):
    return build_graph(model, max_tool_calls=max_tool_calls).invoke(
        {"messages": [HumanMessage(text)]}
    )


def test_compound_question_uses_tool_and_returns_blocks():
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_growth", {"principal": 1000000, "annual_rate": 0.05, "years": 10}),
            AIMessage("10 年后约为 1,628,894.63 元。"),
        ]
    )
    result = run(model)

    tool_msg = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.status == "success"
    assert '"final_value": "1628894.63"' in tool_msg.content

    types = [b["type"] for b in result["ui_blocks"]]
    assert types == ["calculation_result", "line_chart"]
    chart = result["ui_blocks"][1]
    assert chart["series"][0]["points"][-1] == {"x": 10, "y": 1628894.63}
    # 免责声明由代码追加
    assert HYPOTHETICAL_NOTE in result["reply"]


def test_percent_written_as_integer_returns_error_to_llm():
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_growth", {"principal": 1000000, "annual_rate": 5, "years": 10}),
            tool_call(
                "calculate_growth",
                {"principal": 1000000, "annual_rate": 0.05, "years": 10},
                call_id="call_2",
            ),
            AIMessage("已修正。"),
        ]
    )
    result = run(model)
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs[0].status == "error"
    assert "小数形式" in tool_msgs[0].content
    assert tool_msgs[1].status == "success"
    assert len(result["ui_blocks"]) == 2  # 只有成功的调用产生 UI 块


def test_invalid_schema_is_reported_not_raised():
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_growth", {"principal": "很多", "annual_rate": 0.05, "years": 10}),
            AIMessage("请告诉我具体金额。"),
        ]
    )
    result = run(model)
    tool_msg = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.status == "error"
    assert result["ui_blocks"] == []
    assert result["reply"] == "请告诉我具体金额。"


def test_tool_call_limit_stops_loop():
    args = {"principal": 1000, "annual_rate": 0.05, "years": 1}
    model = ScriptedChatModel(
        responses=[tool_call("calculate_growth", args, call_id=f"c{i}") for i in range(10)]
    )
    result = run(model, max_tool_calls=2)
    assert result["reply"].startswith(TOOL_LIMIT_REPLY)
    assert sum(isinstance(m, ToolMessage) for m in result["messages"]) == 2


def test_plain_answer_has_no_disclaimer():
    model = ScriptedChatModel(responses=[AIMessage("七日年化是现金管理类产品常用的收益口径。")])
    result = run(model, text="什么是七日年化？")
    assert result["ui_blocks"] == []
    assert HYPOTHETICAL_NOTE not in result["reply"]


def test_scenarios_tool_sorted_series():
    model = ScriptedChatModel(
        responses=[
            tool_call(
                "generate_return_scenarios",
                {"principal": 1000000, "years": 10, "annual_rates": [0.05, 0.02, 0.03]},
            ),
            AIMessage("对比如图。"),
        ]
    )
    result = run(model)
    names = [s["name"] for s in result["ui_blocks"][0]["series"]]
    assert names == ["年化 2%", "年化 3%", "年化 5%"]


def test_fee_tool():
    model = ScriptedChatModel(
        responses=[
            tool_call(
                "calculate_fees",
                {"amount": 100000, "subscription_fee_rate": 0.003, "holding_period_return": 0.02},
            ),
            AIMessage("到手约 101,694.92 元。"),
        ]
    )
    result = run(model)
    items = {i["label"]: i["value"] for i in result["ui_blocks"][0]["items"]}
    assert items["申购费"] == "299.10"
    assert items["到手金额"] == "101694.92"
