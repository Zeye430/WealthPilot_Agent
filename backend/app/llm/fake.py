"""Fake model for load testing (LLM_PROVIDER=fake): canned replies + simulated latency, no external
calls, no cost.

It measures the system's own throughput and bottlenecks (thread pool, DB pool, review and tool
overhead) with model latency as a controlled variable.
It logs a warning at startup, and readiness and the ops dashboard show provider=fake, so it can't be
mistaken for the real service.
"""

import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

FAKE_ANSWER = (
    "业绩比较基准是产品管理人设定的投资目标参考，不是预期收益率，也不代表产品的实际收益。"
    "银行理财产品不保本，净值会随市场波动。"
)


class FakeChatModel(BaseChatModel):
    reply: str = FAKE_ANSWER
    latency_seconds: float = 1.5
    prompt_tokens: int = 1800  # close to the real system prompt + customer data, for cost estimates
    completion_tokens: int = 120

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        time.sleep(self.latency_seconds)
        usage = {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}
        message = AIMessage(
            self.reply,
            usage_metadata={
                "input_tokens": self.prompt_tokens,
                "output_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
            },
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"token_usage": usage, "model_name": "fake"},
        )
