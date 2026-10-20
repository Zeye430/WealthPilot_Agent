"""Topic router (scope_router): a light classifier before the main agent that controls cost and
service scope.

It can misclassify, so it **carries no compliance responsibility**: even if "recommend a product" is
misread as general knowledge,
the LLM still has no product tools for an unprofiled customer (see app/compliance/policy.py). On
failure it defaults to the main agent.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

FINANCE_KNOWLEDGE = "FINANCE_KNOWLEDGE"
CALCULATION = "CALCULATION"
PRODUCT_OR_ADVICE = "PRODUCT_OR_ADVICE"
HANDOFF = "HANDOFF"
SERVICE = "SERVICE"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
LABELS = (FINANCE_KNOWLEDGE, CALCULATION, PRODUCT_OR_ADVICE, HANDOFF, SERVICE, OUT_OF_SCOPE)
DEFAULT_LABEL = FINANCE_KNOWLEDGE

ROUTER_PROMPT = """你是理财助手的话题分类器。
根据客户最新一条消息（必要时参考上一轮助手回复理解省略的追问），只输出一个标签，不要输出任何其他内容。

FINANCE_KNOWLEDGE：理财、投资、储蓄、利率、风险、费用、监管等金融常识
CALCULATION：收益、复利、定投、通胀、费用等数值测算
PRODUCT_OR_ADVICE：要求推荐、筛选、比较或评价具体理财产品，或询问自己的钱该怎么投、怎么配置
HANDOFF：要求联系人工或理财经理
SERVICE：问候、感谢、询问助手能做什么、风险测评相关
OUT_OF_SCOPE：与理财和本服务无关的问题，如天文地理、写代码、娱乐、闲聊"""

CONTEXT_CHARS = 200


def classify(model: BaseChatModel, messages: list[BaseMessage]) -> str:
    user = messages[-1]
    previous = next((m for m in reversed(messages[:-1]) if isinstance(m, AIMessage)), None)
    content = f"客户最新消息：{user.content}"
    if previous is not None and previous.content:
        content = f"上一轮助手回复（节选）：{str(previous.content)[:CONTEXT_CHARS]}\n\n{content}"
    try:
        output = model.invoke([SystemMessage(ROUTER_PROMPT), HumanMessage(content)]).content
    except Exception:
        logger.warning("scope router failed, falling back to %s", DEFAULT_LABEL, exc_info=True)
        return DEFAULT_LABEL
    text = str(output).strip().upper()
    return next((label for label in LABELS if label in text), DEFAULT_LABEL)
