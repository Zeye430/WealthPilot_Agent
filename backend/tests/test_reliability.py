"""可靠性（P8-4）：故障注入、模型熔断、单轮时长上限、金额必须有来源。

每种故障都验证两件事：系统行为可控（不崩溃、不卡住），以及客户看到明确的提示。
"""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatResult
from sqlalchemy import select

from app.agent.graph import build_graph
from app.agent.prompts import BREAKER_OPEN_REPLY, TURN_TIMEOUT_REPLY
from app.api.chat import get_agent
from app.api.deps import get_current_user
from app.compliance.output_guard import check_output, ungrounded_amounts
from app.compliance.policy import Permission
from app.core.i18n import use_locale
from app.db.models import TurnMetric
from app.db.session import get_engine
from app.llm.breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker, reset_breaker
from app.main import app
from tests.fakes import ScriptedChatModel, tool_call
from tests.test_api_chat import HEADERS, _db_available, use_models

db_required = pytest.mark.skipif(not _db_available(), reason="数据库未启动")


def timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://llm.example/v1"))


class FailingChatModel(BaseChatModel):
    """模拟模型服务故障：每次调用都抛出指定异常，并记录调用次数。"""

    calls: int = 0
    error: str = "timeout"

    @property
    def _llm_type(self) -> str:
        return "failing"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls += 1
        if self.error == "timeout":
            raise timeout_error()
        raise openai.RateLimitError(
            "rate limited",
            response=httpx.Response(429, request=httpx.Request("POST", "https://llm.example")),
            body=None,
        )


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def client():
    reset_breaker()
    c = TestClient(app, headers=HEADERS)
    c.post("/api/v1/demo/reset")
    with get_engine().begin() as conn:
        conn.execute(TurnMetric.__table__.delete())
    yield c
    c.post("/api/v1/demo/reset")
    reset_breaker()
    for dep in [d for d in app.dependency_overrides if d is not get_current_user]:
        app.dependency_overrides.pop(dep)


def outcomes() -> list[str]:
    with get_engine().connect() as conn:
        return list(
            conn.execute(select(TurnMetric.outcome).order_by(TurnMetric.created_at)).scalars()
        )


# ---------- 熔断器（纯逻辑） ----------


def test_breaker_opens_after_consecutive_failures_and_recovers():
    clock = FakeClock()
    b = CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock)
    for _ in range(2):
        b.record_failure()
    assert b.state == CLOSED and b.allow()
    b.record_failure()
    assert b.state == OPEN and not b.allow()
    clock.t += 31
    assert b.state == HALF_OPEN
    assert b.allow()  # 只放行一个探测请求
    assert not b.allow()
    b.record_success()
    assert b.state == CLOSED and b.allow()


def test_breaker_failed_probe_reopens():
    clock = FakeClock()
    b = CircuitBreaker(failure_threshold=1, cooldown_seconds=10, clock=clock)
    b.record_failure()
    clock.t += 11
    assert b.allow()
    b.record_failure()
    assert b.state == OPEN
    assert b.retry_after() == 10


def test_success_resets_failure_count():
    b = CircuitBreaker(failure_threshold=3, cooldown_seconds=10, clock=FakeClock())
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    assert b.state == CLOSED


# ---------- 故障注入（端到端） ----------


@db_required
def test_model_timeout_gives_clear_error_and_counts_toward_breaker(client):
    failing = FailingChatModel()
    app.dependency_overrides[get_agent] = lambda: build_graph(
        failing, ScriptedChatModel(responses=[AIMessage("FINANCE_KNOWLEDGE")] * 10)
    )
    resp = client.post("/api/v1/chat", json={"message": "什么是业绩比较基准"})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "AI 服务暂时不可用，请稍后再试"
    assert outcomes() == ["ERROR"]


@db_required
def test_breaker_opens_and_fails_fast_without_calling_model(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_breaker_failures", 2)
    reset_breaker()
    failing = FailingChatModel(error="rate_limit")
    router = FailingChatModel(error="rate_limit")
    app.dependency_overrides[get_agent] = lambda: build_graph(failing, router)
    for _ in range(2):
        assert client.post("/api/v1/chat", json={"message": "你好"}).status_code == 502
    calls_before = failing.calls + router.calls
    resp = client.post("/api/v1/chat", json={"message": "你好"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == BREAKER_OPEN_REPLY
    assert int(resp.headers["Retry-After"]) > 0
    assert failing.calls + router.calls == calls_before  # 熔断中不再调用模型
    assert outcomes() == ["ERROR", "ERROR", "BREAKER_OPEN"]
    # 熔断期间其他功能照常可用
    assert client.get("/api/v1/products").status_code == 200
    with use_locale("en"):
        client.cookies.set("wp_locale", "en")
        en = client.post("/api/v1/chat", json={"message": "hi"})
        assert en.json()["detail"].startswith("The AI assistant is busy")


@db_required
def test_router_failure_falls_back_and_still_answers(client):
    app.dependency_overrides[get_agent] = lambda: build_graph(
        ScriptedChatModel(responses=[AIMessage("业绩比较基准不是预期收益。")]),
        FailingChatModel(),
    )
    resp = client.post("/api/v1/chat", json={"message": "什么是业绩比较基准"})
    assert resp.status_code == 200
    assert resp.json()["reply"]["content"].startswith("业绩比较基准不是预期收益")


@db_required
def test_tool_internal_error_is_contained(client, monkeypatch):
    """检索服务（向量库）内部异常：工具返回错误，模型照常作答，指标记录工具失败。"""
    import app.tools.document_tools as docs

    def broken(*_args, **_kwargs):
        raise RuntimeError("vector index unavailable")

    monkeypatch.setattr(docs, "get_retriever", broken)
    use_models(
        main=[
            tool_call("search_documents", {"query": "存款保险保多少"}),
            AIMessage("资料暂时无法检索。存款保险的具体规定建议咨询理财经理。"),
        ],
        router=["FINANCE_KNOWLEDGE"],
    )
    resp = client.post("/api/v1/chat", json={"message": "存款保险保多少"})
    assert resp.status_code == 200
    with get_engine().connect() as conn:
        m = conn.execute(select(TurnMetric)).one()
    assert m.tool_errors == 1 and m.outcome == "ANSWERED"


# ---------- 单轮时长上限 ----------


class ClockAdvancingModel(ScriptedChatModel):
    """每次调用后把时钟拨快，模拟一次很慢的模型调用。"""

    clock: FakeClock
    step: float = 0

    model_config = {"arbitrary_types_allowed": True}

    def _generate(self, *args, **kwargs):
        result = super()._generate(*args, **kwargs)
        self.clock.t += self.step
        return result


def test_turn_deadline_stops_calling_model_but_keeps_results():
    clock = FakeClock()
    model = ClockAdvancingModel(
        responses=[
            tool_call("calculate_growth", {"principal": 100000, "annual_rate": 0.03, "years": 5}),
            AIMessage("不应被调用"),
        ],
        clock=clock,
        step=120,  # 第一次调用后时间就已耗尽
    )
    router = ScriptedChatModel(responses=[AIMessage("CALCULATION")])
    graph = build_graph(model, router, clock=clock)
    result = graph.invoke(
        {
            "messages": [HumanMessage("10万3%五年")],
            "permission": Permission.ASSESSED,
            "risk_rating": "C2",
            "policy_decisions": [],
            "deadline": clock.t + 60,
        }
    )
    assert model.calls == 1
    assert result["reply"].startswith(TURN_TIMEOUT_REPLY)
    assert "calculation_result" in [b["type"] for b in result["ui_blocks"]]  # 已算出的结果照常展示
    assert any(d["decision"] == "TIMEOUT" for d in result["policy_decisions"])


# ---------- 金额必须有来源 ----------


def test_model_arithmetic_amount_is_flagged():  # 2b 英文场景评估 P04
    facts = '{"subscription_fee": "0.00", "redemption_fee": "500.00", "net_proceeds": "99500.00"}'
    facts += "\n客户：我买了10万元知岸稳享每日开放，持有5天就赎回"
    wrong = "赎回费 500 元，到手约 95,500 元。"
    assert ungrounded_amounts(wrong, facts) == ["95,500 元"]
    assert "O-UNGROUNDED_AMOUNT" in check_output(wrong, Permission.ASSESSED, facts=facts)
    right = "赎回费 500 元，到手 99,500 元；您投入的 10万元 不收申购费。"
    assert ungrounded_amounts(right, facts) == []


def test_amount_rounding_and_units_are_tolerated():
    facts = '{"final_value": "1628894.63", "total_gain": "628894.63"}  客户：100万'
    assert ungrounded_amounts("约 162.89 万元，收益约 62.9 万元", facts) == []
    assert ungrounded_amounts("about ¥1.63 million (¥628,895 gain) on ¥1,000,000", facts) == []
    assert ungrounded_amounts("约 170 万元", facts) == ["170 万元"]


def test_knowledge_base_amounts_count_as_grounded():
    # 存款保险 50 万元来自已核对原文的知识库
    assert ungrounded_amounts("存款保险最高偿付 50 万元。", "") == []


def test_customer_profile_amounts_are_grounded():
    facts = "- 在本行资产：活期存款 15 万元，定期存款 30 万元"
    assert ungrounded_amounts("您的活期存款约 15 万元。", facts) == []
    assert ungrounded_amounts("加上这 20 万，一共 35 万元。", facts + " 客户：这20万") == [
        "35 万元"
    ]


def test_illustrative_amount_allowed_when_marked_as_assumption():
    # 产品负责人决定（2026-10-19）：常识讲解可以用整数金额举例，但同一句要说明是假设
    zh = "假设您在同一家银行存了 60 万元，存款保险最高偿付 50 万元。"
    assert ungrounded_amounts(zh, "") == []
    assert ungrounded_amounts("例如投入 10 万元、年化 3%，具体收益以测算结果为准。", "") == []
    en = "For example, say you have ¥600,000 at one bank: coverage is capped at ¥500,000."
    assert ungrounded_amounts(en, "") == []
    split = "Coverage is per bank (e.g. ¥1.5 million split across banks)."
    assert ungrounded_amounts(split, "") == []
    # 同一金额在后文再次提到时沿用该假设
    assert ungrounded_amounts(zh + "这 60 万元中超出限额的部分不受保障。", "") == []


def test_illustrative_amount_without_assumption_marker_is_flagged():
    assert ungrounded_amounts("您在同一家银行存了 60 万元。", "") == ["60 万元"]
    # 假设写在另一句里不算：标记必须和金额在同一句
    assert ungrounded_amounts("我们举个例子。您存了 60 万元。", "") == ["60 万元"]


def test_calculated_result_in_assumption_sentence_is_still_flagged():
    # 举例的输入可以是假设，计算结果仍须来自工具（模型不能自己算）
    zh = "假设投入 10 万元、年化 3%，一年后约 10.3 万元。"
    assert ungrounded_amounts(zh, "") == ["10.3 万元"]
    en = "Suppose you invest ¥1,000,000 at 6% for 10 years; it grows to ¥1,790,848."
    assert ungrounded_amounts(en, "") == ["¥1,790,848"]


# ---------- 数据库连接池耗尽 ----------


@db_required
def test_pool_exhaustion_returns_busy_503(client):
    """P8-4 压测发现：并发超过连接池容量时原先等 30 秒后返回笼统的 500。"""
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError

    from app.db.session import get_session

    def exhausted():
        raise PoolTimeoutError("QueuePool limit reached")

    app.dependency_overrides[get_session] = exhausted
    resp = client.get("/api/v1/products")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "系统繁忙，请稍后再试。"
    assert resp.headers["Retry-After"] == "5"


def test_amount_tolerance_catches_extra_zero():  # 英文评估 P04：99,500 写成 995,000
    facts = '{"net_proceeds": "99500.00"} 客户资料：总资产 1,000,000'
    assert ungrounded_amounts("Your net proceeds would be ¥995,000.", facts) == ["¥995,000"]


def test_english_product_name_ignores_punctuation():  # 英文评估 R02
    from app.products.catalog import load_catalog

    assert load_catalog().find_by_name("Zhian Steady 1 Year Holding").code == "ZA-F03"
    assert load_catalog().find_by_name("zhian steady 1-year holding").code == "ZA-F03"
    from app.products.service import SearchFilters, _matches

    product = load_catalog().get("ZA-F03")
    assert _matches(product, SearchFilters(keyword="Steady 1 Year Holding"))
