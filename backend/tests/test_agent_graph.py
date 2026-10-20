"""Agent flow tests (scripted fake model, no real LLM calls)."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_graph, latest_allocation_only
from app.agent.prompts import (
    ASSESSMENT_REQUIRED_REPLY,
    OUT_OF_SCOPE_REPLY,
    SAFE_FALLBACK_REPLY,
    TOOL_LIMIT_REPLY,
)
from app.compliance import output_guard
from app.compliance.policy import Permission
from app.tools.calculation_tools import HYPOTHETICAL_NOTE
from tests.fakes import ScriptedChatModel, tool_call

GROWTH_ARGS = {"principal": 1000000, "annual_rate": 0.05, "years": 10}


def run(
    model,
    label="CALCULATION",
    text="100万按每年5%复利10年是多少？",
    permission=Permission.ASSESSED,
    rating="C2",
    max_tool_calls=6,
    router=None,
):
    router = router or ScriptedChatModel(responses=[AIMessage(label)])
    graph = build_graph(model, router, max_tool_calls=max_tool_calls)
    return graph.invoke(
        {
            "messages": [HumanMessage(text)],
            "permission": permission,
            "risk_rating": rating if permission is Permission.ASSESSED else None,
            "gate_reasons": [] if permission is Permission.ASSESSED else ["ASSESSMENT_MISSING"],
            "policy_decisions": [],
        }
    )


def block_types(result):
    return [b["type"] for b in result["ui_blocks"]]


def decisions(result, checkpoint):
    return [d for d in result["policy_decisions"] if d["checkpoint"] == checkpoint]


# ---------- Calculation path (Phase 1 regression) ----------


def test_compound_question_uses_tool_and_returns_blocks():
    model = ScriptedChatModel(
        responses=[tool_call("calculate_growth", GROWTH_ARGS), AIMessage("约 1,628,894.63 元。")]
    )
    result = run(model)
    tool_msg = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert '"final_value": "1628894.63"' in tool_msg.content
    assert block_types(result) == ["calculation_result", "line_chart"]
    assert result["ui_blocks"][1]["series"][0]["points"][-1] == {"x": 10, "y": 1628894.63}
    assert HYPOTHETICAL_NOTE in result["reply"]


def test_percent_written_as_integer_returns_error_to_llm():
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_growth", {**GROWTH_ARGS, "annual_rate": 5}),
            tool_call("calculate_growth", GROWTH_ARGS, call_id="call_2"),
            AIMessage("已修正。"),
        ]
    )
    result = run(model)
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs[0].status == "error" and "小数形式" in tool_msgs[0].content
    assert tool_msgs[1].status == "success"
    assert len(result["ui_blocks"]) == 2


def test_invalid_schema_is_reported_not_raised():
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_growth", {**GROWTH_ARGS, "principal": "很多"}),
            AIMessage("请告诉我具体金额。"),
        ]
    )
    result = run(model)
    assert next(m for m in result["messages"] if isinstance(m, ToolMessage)).status == "error"
    assert result["ui_blocks"] == []


def test_tool_call_limit_stops_loop():
    model = ScriptedChatModel(
        responses=[tool_call("calculate_growth", GROWTH_ARGS, call_id=f"c{i}") for i in range(10)]
    )
    result = run(model, max_tool_calls=2)
    assert result["reply"].startswith(TOOL_LIMIT_REPLY)
    assert sum(isinstance(m, ToolMessage) for m in result["messages"]) == 2


def test_tool_limit_summarizes_existing_results():  # scenario V02
    calls = [tool_call("calculate_growth", GROWTH_ARGS, call_id=f"c{i}") for i in range(3)]
    model = ScriptedChatModel(responses=[*calls, AIMessage("按 5% 测算，10 年后约 162.89 万元。")])
    result = run(model, max_tool_calls=2)
    # The 3rd call isn't executed; the model answers from the first two results; charts already
    # produced are still shown
    assert result["reply"].startswith("按 5% 测算")
    assert sum(isinstance(m, ToolMessage) for m in result["messages"]) == 2
    assert "calculation_result" in block_types(result)
    assert decisions(result, "TOOL")[-1]["decision"] == "TOOL_LIMIT_SUMMARY"


def test_simulation_count_is_per_turn():
    from app.tools.profile_tools import MAX_SIMULATIONS_PER_TURN, _simulations_this_turn

    sim = {"allocations": [{"product": "知岸活钱宝", "amount": 100000}]}
    earlier_turn = [HumanMessage("上次"), tool_call("simulate_allocation", sim, "a")]
    this_turn = [
        HumanMessage("帮我配置"),
        tool_call("simulate_allocation", sim, "b"),
        tool_call("simulate_allocation", sim, "c"),
    ]
    assert _simulations_this_turn({"messages": [*earlier_turn, *this_turn]}) == 2
    extra = [*earlier_turn, *this_turn, tool_call("simulate_allocation", sim, "d")]
    assert _simulations_this_turn({"messages": extra}) > MAX_SIMULATIONS_PER_TURN


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
    names = [s["name"] for s in run(model)["ui_blocks"][0]["series"]]
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
    items = {i["label"]: i["value"] for i in run(model)["ui_blocks"][0]["items"]}
    assert items["申购费"] == "299.10"
    assert items["到手金额"] == "101694.92"


# ---------- Topic routing ----------


def test_out_of_scope_never_calls_main_model():  # S02c / S02d
    for permission in Permission:
        model = ScriptedChatModel(responses=[])
        result = run(model, label="OUT_OF_SCOPE", text="太阳离地球多远？", permission=permission)
        assert model.calls == 0
        assert result["reply"] == OUT_OF_SCOPE_REPLY
        assert result["ui_blocks"] == []


def test_router_output_with_extra_text_is_parsed():
    model = ScriptedChatModel(responses=[])
    result = run(model, label="标签：OUT_OF_SCOPE", text="帮我写段代码")
    assert result["reply"] == OUT_OF_SCOPE_REPLY


def test_router_failure_falls_back_to_agent():
    broken_router = ScriptedChatModel(responses=[])  # raises IndexError when called
    model = ScriptedChatModel(responses=[AIMessage("七日年化是一种收益口径。")])
    result = run(model, router=broken_router, text="什么是七日年化？")
    assert model.calls == 1
    assert decisions(result, "ROUTER")[0]["decision"] == "FINANCE_KNOWLEDGE"


# ---------- Assessment gate ----------


def test_product_request_before_assessment_is_blocked_without_llm():  # S01 / S02e
    model = ScriptedChatModel(responses=[])
    result = run(
        model,
        label="PRODUCT_OR_ADVICE",
        text="有什么理财推荐？",
        permission=Permission.ASSESSMENT_REQUIRED,
    )
    assert model.calls == 0
    assert result["reply"] == ASSESSMENT_REQUIRED_REPLY
    assert result["ui_blocks"][0]["type"] == "assessment_prompt"
    assert result["ui_blocks"][0]["variant"] == "invite"
    gate = decisions(result, "GATE")[0]
    assert gate["decision"] == "BLOCK_PRODUCT_REQUEST"
    assert gate["reason_codes"] == ["ASSESSMENT_MISSING"]


def test_product_request_after_assessment_reaches_agent():
    model = ScriptedChatModel(responses=[AIMessage("产品查询功能即将开放。")])
    result = run(model, label="PRODUCT_OR_ADVICE", text="有什么理财推荐？")
    assert model.calls == 1
    assert "assessment_prompt" not in block_types(result)


def test_knowledge_before_assessment_gets_reminder():  # S02
    model = ScriptedChatModel(
        responses=[AIMessage("业绩比较基准是产品的投资目标参考，不代表承诺。")]
    )
    result = run(
        model,
        label="FINANCE_KNOWLEDGE",
        text="什么是业绩比较基准？",
        permission=Permission.ASSESSMENT_REQUIRED,
    )
    # A general answer without retrieved sources: labeled "general information", with an assessment
    # reminder
    assert block_types(result) == ["source_note", "assessment_prompt"]
    assert result["ui_blocks"][1]["variant"] == "reminder"


def test_general_calculation_allowed_before_assessment():  # S02b
    model = ScriptedChatModel(
        responses=[tool_call("calculate_growth", GROWTH_ARGS), AIMessage("约 162.89 万元。")]
    )
    result = run(model, permission=Permission.ASSESSMENT_REQUIRED)
    assert block_types(result) == ["calculation_result", "line_chart", "assessment_prompt"]


def test_unbound_tool_is_blocked_at_execution():
    # The model "hallucinates" a call to a tool that isn't bound before an assessment: the execution
    # layer blocks it again
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_fees", {"amount": 100000, "subscription_fee_rate": 0.003}),
            AIMessage("该测算需要先完成风险测评。"),
        ]
    )
    result = run(model, permission=Permission.ASSESSMENT_REQUIRED)
    tool_msg = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.status == "error"
    assert decisions(result, "TOOL")[0]["reason_codes"] == ["TOOL:calculate_fees"]
    assert "calculation_result" not in block_types(result)


# ---------- Output review ----------


def test_prohibited_claim_is_rewritten():
    model = ScriptedChatModel(
        responses=[AIMessage("这类产品保证收益 5%。"), AIMessage("这类产品不保证收益，可能亏损。")]
    )
    result = run(model, label="FINANCE_KNOWLEDGE", text="固收理财收益怎么样？")
    assert model.calls == 2
    assert result["reply"] == "这类产品不保证收益，可能亏损。"
    assert decisions(result, "OUTPUT")[0]["decision"] == "REWRITE"


def test_repeated_violation_falls_back():
    model = ScriptedChatModel(responses=[AIMessage("稳赚不赔。"), AIMessage("保证收益。")])
    result = run(model, label="FINANCE_KNOWLEDGE", text="这个稳吗？")
    assert result["reply"] == SAFE_FALLBACK_REPLY
    assert [d["decision"] for d in decisions(result, "OUTPUT")] == ["REWRITE", "FALLBACK"]


def test_rejected_draft_cannot_ground_the_rewrite():
    # Found in scenario R01: a rejected draft used to count as an earlier message, so repeating the
    # same made-up amount in the rewrite passed
    draft = "超出限额部分为 11.2 万元。"
    model = ScriptedChatModel(responses=[AIMessage(draft), AIMessage(draft)])
    result = run(model, label="FINANCE_KNOWLEDGE", text="能举个例子说明超过限额的部分怎么算吗？")
    assert result["reply"] == SAFE_FALLBACK_REPLY
    assert [d["decision"] for d in decisions(result, "OUTPUT")] == ["REWRITE", "FALLBACK"]


def test_rejected_draft_cannot_ground_a_product():
    # The same bug affected product grounding: a product invented in the draft can't vouch for the
    # rewrite
    draft = "推荐知岸稳享每日开放。"
    model = ScriptedChatModel(responses=[AIMessage(draft), AIMessage(draft)])
    result = run(model, label="PRODUCT", text="有什么稳健的产品？")
    assert result["reply"] == SAFE_FALLBACK_REPLY


def test_tool_result_in_rewrite_still_grounds_amount():
    # An amount from a tool called during the rewrite is a legitimate source
    model = ScriptedChatModel(
        responses=[
            AIMessage("约 170 万元。"),
            tool_call("calculate_growth", GROWTH_ARGS),
            AIMessage("约 1,628,894.63 元。"),
        ]
    )
    result = run(model)
    assert result["reply"].startswith("约 1,628,894.63 元。")
    assert [d["decision"] for d in decisions(result, "OUTPUT")] == ["REWRITE"]


def test_repeated_steering_is_redacted_instead_of_fallback():
    steer = "想要更高收益的话，您可以重新评估风险承受能力。"
    model = ScriptedChatModel(
        responses=[
            AIMessage(f"您的评级为 C2。{steer}"),
            AIMessage(f"您的评级为 C2，可购买 PR2 及以下产品。{steer}"),
        ]
    )
    result = run(model, label="FINANCE_KNOWLEDGE", text="我能承受高风险")
    assert result["reply"] == "您的评级为 C2，可购买 PR2 及以下产品。"
    assert [d["decision"] for d in decisions(result, "OUTPUT")] == ["REWRITE", "REDACT"]


def test_guarantee_question_gets_explicit_denial():
    evasive = "风险最低的是现金管理类产品。银行存款受存款保险保障。"
    result = run(
        ScriptedChatModel(responses=[AIMessage(evasive)]),
        label="FINANCE_KNOWLEDGE",
        text="哪款产品是保本保收益的？",
    )
    assert result["reply"].endswith(output_guard.NO_GUARANTEE_NOTE)

    explicit = "银行理财产品不保本，也不承诺收益。"
    result = run(
        ScriptedChatModel(responses=[AIMessage(explicit)]),
        label="FINANCE_KNOWLEDGE",
        text="哪款产品是保本保收益的？",
    )
    assert result["reply"] == explicit


def test_own_holding_mentioned_before_assessment_is_not_a_leak():  # scenario R01
    reply = "存款保险最高偿付 50 万元；您持有的知岸活钱宝属于理财产品，不在存款保险范围内。"
    graph = build_graph(
        ScriptedChatModel(responses=[AIMessage(reply)]),
        ScriptedChatModel(responses=[AIMessage("FINANCE_KNOWLEDGE")]),
    )
    result = graph.invoke(
        {
            "messages": [HumanMessage("银行倒闭了我的钱能赔多少？")],
            "permission": Permission.ASSESSMENT_REQUIRED,
            "risk_rating": None,
            "gate_reasons": ["ASSESSMENT_MISSING"],
            "policy_decisions": [],
            "customer_context": "- 在本行资产：理财持仓 知岸活钱宝 5 万元",
        }
    )
    assert result["reply"].startswith("存款保险最高偿付")
    assert decisions(result, "OUTPUT") == []


def test_recommendation_before_assessment_is_rewritten():
    model = ScriptedChatModel(
        responses=[
            AIMessage("我建议您购买固收类理财。"),
            AIMessage("完成风险测评后，我才能为您筛选产品。"),
        ]
    )
    result = run(
        model,
        label="FINANCE_KNOWLEDGE",
        text="固收理财适合我吗？",
        permission=Permission.ASSESSMENT_REQUIRED,
    )
    codes = decisions(result, "OUTPUT")[0]["reason_codes"]
    # the audit record includes the offending snippet
    assert codes == ["O-PERMISSION_LEAK", "片段:建议您购买"]
    assert "建议您购买" not in result["reply"]


# ---------- Product tools (Phase 3) ----------


def test_search_products_uses_injected_rating():
    model = ScriptedChatModel(
        responses=[
            tool_call("search_products", {"max_lockup_days": 0}),
            AIMessage("在您的风险等级范围内，有几款每日开放的产品，详见列表。"),
        ]
    )
    result = run(model, label="PRODUCT_OR_ADVICE", text="有什么随时能取的产品？", rating="C2")
    block = result["ui_blocks"][0]
    assert block["type"] == "product_list"
    assert {i["code"] for i in block["items"]} == {"ZA-C01", "HY-C01", "ZA-F01"}
    assert "PR2" in block["title"]


def test_llm_cannot_pass_rating_to_widen_results():
    # Even if the model tries to pass a risk_rating argument, the tool only trusts the rating in the
    # flow state
    model = ScriptedChatModel(
        responses=[
            tool_call("search_products", {"risk_rating": "C5", "product_types": ["EQUITY"]}),
            AIMessage("在您的风险等级范围内没有权益类产品。"),
        ]
    )
    result = run(model, label="PRODUCT_OR_ADVICE", text="给我看权益类", rating="C2")
    items = next(b for b in result["ui_blocks"] if b["type"] == "product_list")["items"]
    assert items == []


def test_product_tools_unavailable_before_assessment():
    model = ScriptedChatModel(
        responses=[
            tool_call("search_products", {}),
            AIMessage("完成风险测评后才能查询产品。"),
        ]
    )
    result = run(model, label="FINANCE_KNOWLEDGE", permission=Permission.ASSESSMENT_REQUIRED)
    assert decisions(result, "TOOL")[0]["reason_codes"] == ["TOOL:search_products"]
    assert "product_list" not in block_types(result)


def test_made_up_product_is_rewritten():
    model = ScriptedChatModel(
        responses=[
            AIMessage("可以考虑知岸权益精选。"),
            AIMessage("我可以先帮您在风险等级范围内搜索产品。"),
        ]
    )
    result = run(model, label="PRODUCT_OR_ADVICE", text="有什么好产品？")
    codes = decisions(result, "OUTPUT")[0]["reason_codes"]
    # Both made up (not queried this turn) and a PR5 product recommended to a C2 customer
    assert codes[:2] == ["O-UNGROUNDED_PRODUCT", "O-UNSUITABLE_RECOMMENDATION"]


def test_product_fee_rates_come_from_catalog_not_llm():
    # Even if the model passes a wrong fee rate, the prospectus wins once product is set: redemption
    # within 7 days costs 0.5% for Zhian Steady Daily Open
    model = ScriptedChatModel(
        responses=[
            tool_call(
                "calculate_fees",
                {
                    "amount": 100000,
                    "product": "知岸稳享每日开放",
                    "holding_days": 5,
                    "redemption_fee_rate": 0.1,
                },
            ),
            AIMessage("赎回费 500 元。"),
        ]
    )
    block = run(model)["ui_blocks"][0]
    items = {i["label"]: i["value"] for i in block["items"]}
    assert items["赎回费"] == "500.00"
    assert block["assumptions"][0].startswith("费率来自《知岸稳享每日开放》说明书")


def test_product_fee_requires_holding_days():
    model = ScriptedChatModel(
        responses=[
            tool_call("calculate_fees", {"amount": 100000, "product": "ZA-F01"}),
            AIMessage("请告诉我持有天数。"),
        ]
    )
    result = run(model)
    tool_msg = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.status == "error" and "持有天数" in tool_msg.content


# scenario V02: drafts shown next to the final plan would contradict each other
def test_only_last_allocation_shown():
    blocks = [
        {"type": "product_list", "items": []},
        {"type": "allocation", "title": "草稿"},
        {"type": "allocation", "title": "调整后"},
    ]
    assert [b.get("title") for b in latest_allocation_only(blocks)] == [None, "调整后"]
    mixed = [
        {"type": "allocation", "title": "通过", "passed": True},
        {"type": "allocation", "title": "未通过", "passed": False},
    ]
    assert [b["title"] for b in latest_allocation_only(mixed)] == ["通过"]
