"""模型调用遥测：一轮对话中每次模型调用的用途、耗时、token 与错误。

通过 LangChain 回调收集（agent.invoke 的 config 传入），图中各节点内部的 model.invoke 会自动继承，
业务代码无需改动。调用用途来自 LangGraph 附带的节点名：scope_router → router，agent → agent，
tool_limit → summary。只记录数字，不记录提示词与回答内容。
"""

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.config import get_settings

NODE_ROLES = {"scope_router": "router", "agent": "agent", "tool_limit": "summary"}


@dataclass
class LLMCall:
    role: str
    model: str
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


@dataclass
class TurnTelemetry(BaseCallbackHandler):
    calls: list[LLMCall] = field(default_factory=list)
    _starts: dict[UUID, tuple[float, str, str]] = field(default_factory=dict)

    # LangChain 会对回调做浅拷贝等处理，显式声明为线程安全以便在工具线程中使用
    run_inline = True

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list,
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        invocation_params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node = (metadata or {}).get("langgraph_node", "")
        model = (invocation_params or {}).get("model") or (invocation_params or {}).get(
            "model_name", ""
        )
        self._starts[run_id] = (time.perf_counter(), NODE_ROLES.get(node, node or "other"), model)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        start, role, model = self._starts.pop(run_id, (time.perf_counter(), "other", ""))
        prompt, completion = _usage(response)
        self.calls.append(LLMCall(role, model, time.perf_counter() - start, prompt, completion))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        start, role, model = self._starts.pop(run_id, (time.perf_counter(), "other", ""))
        self.calls.append(
            LLMCall(role, model, time.perf_counter() - start, error=type(error).__name__)
        )

    @property
    def prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.calls)

    @property
    def errors(self) -> int:
        return sum(c.error is not None for c in self.calls)

    @property
    def successes(self) -> int:
        return sum(c.error is None for c in self.calls)

    @property
    def llm_seconds(self) -> float:
        return sum(c.latency_s for c in self.calls)

    @property
    def model(self) -> str:
        return next((c.model for c in self.calls if c.role == "agent" and c.model), "")

    def cost_usd(self) -> Decimal:
        return estimate_cost(self.prompt_tokens, self.completion_tokens)


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> Decimal:
    """按配置的单价（美元 / 百万 token）估算；单价以模型服务商官网为准。"""
    s = get_settings()
    million = Decimal(1_000_000)
    cost = (
        Decimal(prompt_tokens) * Decimal(str(s.llm_price_input_per_mtok))
        + Decimal(completion_tokens) * Decimal(str(s.llm_price_output_per_mtok))
    ) / million
    return cost.quantize(Decimal("0.000001"))


def _usage(response: LLMResult) -> tuple[int, int]:
    usage = (response.llm_output or {}).get("token_usage") or {}
    if usage:
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    for generations in response.generations:
        for g in generations:
            meta = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
            if meta:
                return int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0)
    return 0, 0
