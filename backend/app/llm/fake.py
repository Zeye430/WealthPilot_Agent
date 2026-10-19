"""压测专用假模型（LLM_PROVIDER=fake）：固定回复 + 模拟延迟，不调用外部服务、不计费。

用途是测系统本身的吞吐与瓶颈（线程池、数据库连接池、审查与工具开销），把模型延迟当作可控变量。
启动时会打印警告；就绪检查与运维看板显示 provider=fake，避免误用于真实服务。
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
    prompt_tokens: int = 1800  # 接近真实系统提示词 + 客户资料的规模，便于估算费用
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
