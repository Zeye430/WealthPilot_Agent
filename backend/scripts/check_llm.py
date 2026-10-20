"""Check the configured model: one tool-calling smoke test through the real agent, any provider.

Usage (from backend/): uv run python scripts/check_llm.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage  # noqa: E402

from app.agent.graph import build_graph  # noqa: E402
from app.api.chat import ROUTER_MAX_TOKENS  # noqa: E402
from app.compliance.policy import Permission  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import (  # noqa: E402
    LLMNotConfiguredError,
    get_chat_model,
    get_router_model,
    provider_name,
)


def main() -> None:
    settings = get_settings()
    try:
        model = get_chat_model(settings)
        router = get_router_model(settings, max_tokens=ROUTER_MAX_TOKENS)
    except LLMNotConfiguredError as exc:
        sys.exit(f"{exc}（复制 .env.example 为仓库根目录的 .env 并填写）")

    router_name = settings.llm_router_model or settings.llm_model
    print(f"提供方：{provider_name(settings)}　模型：{settings.llm_model}　路由模型：{router_name}")
    print("运行一次工具调用测试…")
    graph = build_graph(model, router)
    result = graph.invoke(
        {
            "messages": [HumanMessage("100万按每年5%复利10年是多少？")],
            "permission": Permission.ASSESSED,
            "risk_rating": "C2",
            "gate_reasons": [],
            "policy_decisions": [],
        }
    )
    called = [c["name"] for m in result["messages"] for c in getattr(m, "tool_calls", [])]
    print("调用的工具：", called or "无")
    print("回答：", result["reply"])
    reply = result["reply"].replace(",", "").replace(" ", "")
    # Accept the exact amount or the rounded 万 form (162.89万); both come from the tool result
    ok = "calculate_growth" in called and ("1628894.63" in reply or "162.89万" in reply)
    print("\n结果：", "通过 ✅" if ok else "需要检查 ⚠️（未调用工具或数字不一致）")
    print("提示：换用新模型后，请再运行 evaluations/run_scenarios.py 做完整的场景评估。")


if __name__ == "__main__":
    main()
