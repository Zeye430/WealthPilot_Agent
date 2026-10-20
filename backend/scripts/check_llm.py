"""Check Kimi connectivity: list available models and run one tool-calling smoke test with the real
model.

Usage (from backend/): uv run python scripts/check_llm.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from app.agent.graph import build_graph  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import get_chat_model  # noqa: E402


def main() -> None:
    settings = get_settings()
    key = settings.llm_api_key.get_secret_value()
    if not key:
        sys.exit("未配置 LLM_API_KEY：请复制 .env.example 为仓库根目录的 .env 并填写")

    resp = httpx.get(
        f"{settings.llm_base_url}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20
    )
    resp.raise_for_status()
    models = sorted(m["id"] for m in resp.json()["data"])
    print("可用模型：", ", ".join(models))
    if settings.llm_model not in models:
        sys.exit(f"当前配置的 LLM_MODEL={settings.llm_model} 不在列表中，请修改 .env")

    print(f"\n使用 {settings.llm_model} 进行工具调用测试…")
    graph = build_graph(get_chat_model(settings))
    result = graph.invoke({"messages": [HumanMessage("100万按每年5%复利10年是多少？")]})
    called = [c["name"] for m in result["messages"] for c in getattr(m, "tool_calls", [])]
    print("调用的工具：", called or "无")
    print("回答：", result["reply"])
    reply = result["reply"].replace(",", "").replace(" ", "")
    # Accept the exact amount or the rounded 万 form (162.89万); both come from the tool result
    ok = "calculate_growth" in called and ("1628894.63" in reply or "162.89万" in reply)
    print("\n结果：", "通过 ✅" if ok else "需要检查 ⚠️（未调用工具或数字不一致）")


if __name__ == "__main__":
    main()
