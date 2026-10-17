"""输出审查：回答发出前的确定性检查，不调用 LLM。

规则针对**肯定句式**：「理财产品不保本」是合法的事实陈述，「保证收益」才是违规承诺。
"""

import re

from app.compliance.policy import Permission

# 命中前若出现这些否定词（相距不超过 NEGATION_WINDOW 个字），视为否定陈述，不算违规
NEGATIONS = ("不", "非", "没有", "无法", "不能", "不会", "并非", "绝非", "未")
NEGATION_WINDOW = 4

PROHIBITED_CLAIMS = [
    re.compile(p)
    for p in (
        r"保证.{0,6}(收益|回报|本金|不亏)",
        r"保本保收益",
        r"稳赚",
        r"(零|无)风险",
        r"(一定|肯定|必然|绝对)(能|会|可以)?(赚|盈利|达到|获得|翻倍)",
        r"包赚",
    )
]

# 测评前不得出现的推荐类表述
RECOMMENDATION = [
    re.compile(p)
    for p in (
        r"(推荐|建议)(您|你)?(购买|买入|配置|选择|入手)",
        r"适合(您|你)的(理财)?产品(是|有)",
    )
]


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - NEGATION_WINDOW) : start]
    return any(n in window for n in NEGATIONS)


def _affirmative_hits(text: str, patterns: list[re.Pattern]) -> list[str]:
    return [m.group() for p in patterns for m in p.finditer(text) if not _negated(text, m.start())]


def check_output(reply: str, permission: Permission) -> list[str]:
    """返回违规代码列表；空列表表示通过。"""
    violations = []
    if _affirmative_hits(reply, PROHIBITED_CLAIMS):
        violations.append("O-PROHIBITED_CLAIM")
    if permission is Permission.ASSESSMENT_REQUIRED and _affirmative_hits(reply, RECOMMENDATION):
        violations.append("O-PERMISSION_LEAK")
    return violations


def describe(violations: list[str], reply: str) -> str:
    """给 LLM 的改写反馈。"""
    hits = _affirmative_hits(reply, PROHIBITED_CLAIMS) + _affirmative_hits(reply, RECOMMENDATION)
    return (
        "你的上一条回答未通过合规审查（"
        + "、".join(violations)
        + f"），问题表述：{'、'.join(dict.fromkeys(hits))}。"
        "请改写：不得承诺收益或保本；客户未完成风险测评时不得推荐任何产品。只输出改写后的回答。"
    )
