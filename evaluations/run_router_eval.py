"""Evaluate topic-routing accuracy with the real LLM.

Usage (from backend/): uv run python ../evaluations/run_router_eval.py
"""

import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yaml  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from app.agent.router import OUT_OF_SCOPE, classify  # noqa: E402
from app.api.chat import ROUTER_MAX_TOKENS  # noqa: E402
from app.llm.client import get_router_model  # noqa: E402


def main() -> None:
    cases = yaml.safe_load((ROOT / "evaluations/router_cases.yaml").read_text(encoding="utf-8"))
    model = get_router_model(max_tokens=ROUTER_MAX_TOKENS)
    wrong, latencies, per_label = [], [], Counter()

    for case in cases:
        messages = [HumanMessage(case["text"])]
        if prev := case.get("previous"):
            messages = [HumanMessage("（上一轮问题）"), AIMessage(prev), *messages]
        start = time.perf_counter()
        got = classify(model, messages)
        latencies.append(time.perf_counter() - start)
        per_label[case["expected"]] += 1
        ok = got == case["expected"]
        print(f"{'✅' if ok else '❌'} {case['text'][:24]:<26} 期望 {case['expected']:<18} 实际 {got}")
        if not ok:
            wrong.append((case, got))

    n = len(cases)
    latencies.sort()
    print(f"\n准确率：{n - len(wrong)}/{n} = {(n - len(wrong)) / n:.0%}")
    print(f"延迟：中位数 {latencies[n // 2]:.2f}s，最大 {latencies[-1]:.2f}s")
    # The errors that matter most: off-topic questions let through (wasted tokens) or financial
    # questions refused (bad experience)
    leaked = [c for c, g in wrong if c["expected"] == OUT_OF_SCOPE]
    refused = [c for c, g in wrong if g == OUT_OF_SCOPE]
    print(f"无关问题被放行：{len(leaked)} 条；金融问题被误拒：{len(refused)} 条")


if __name__ == "__main__":
    main()
