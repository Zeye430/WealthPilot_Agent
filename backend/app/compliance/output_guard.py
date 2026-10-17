"""输出审查：回答发出前的确定性检查，不调用 LLM。

规则针对**肯定句式**：「理财产品不保本」是合法的事实陈述，「保证收益」才是违规承诺。
"""

import re
from collections.abc import Collection

from app.compliance.policy import Permission
from app.products.catalog import load_catalog

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


# 真实理财公司名称：产品负责人决定产品中不出现任何真实机构的产品信息（演示只用虚构机构）
REAL_INSTITUTIONS = (
    "工银理财",
    "建信理财",
    "农银理财",
    "中银理财",
    "交银理财",
    "中邮理财",
    "招银理财",
    "兴银理财",
    "信银理财",
    "光大理财",
    "平安理财",
    "华夏理财",
    "浦银理财",
    "民生理财",
    "广银理财",
    "渤银理财",
    "恒丰理财",
    "汇华理财",
    "贝莱德建信理财",
    "施罗德交银理财",
    "高盛工银理财",
    "宁银理财",
    "杭银理财",
    "徽银理财",
    "南银理财",
    "青银理财",
    "苏银理财",
    "上银理财",
    "北银理财",
    "渝农商理财",
)


# 诱导调高风险评级：为达到收益目标而建议重新测评，是销售适当性中的典型违规（测评应反映客户真实情况）
REASSESSMENT = re.compile(r"重新(测评|评估)|调(整|高).{0,4}(评级|风险等级)|提高.{0,4}风险承受")
RISK_OR_RETURN = re.compile(r"收益|更高(的)?风险|高风险|PR[3-5]|波动")
SENTENCE_SPLIT = re.compile(r"[。！？；\n]")
# 个性化推荐结论：MVP 默认不输出（docs/COMPLIANCE_DESIGN.md §8）
PERSONALIZED = [
    re.compile(p) for p in (r"适合(您|你)", r"(推荐|建议)(您|你)?(购买|买入|配置|选择|入手)")
]


# 宣称已接通人工：AI 只在理财经理未接手时回复，此时任何「已接入」都不属实
FALSE_HANDOFF = [
    re.compile(p)
    for p in (
        r"(已|已经)(为您|帮您)?(接通|转接|连线|联系上)",
        r"(已|已经)(为您|帮您)?(联系|通知)(了)?.{0,8}(理财经理|经理|人工|客服)",
        r"(理财经理|经理|人工客服).{0,6}(已|已经|正在)(接入|接单|上线|在线|为您服务|处理您)",
    )
]


def steers_reassessment(text: str) -> bool:
    return any(
        REASSESSMENT.search(s) and RISK_OR_RETURN.search(s) for s in SENTENCE_SPLIT.split(text)
    )


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - NEGATION_WINDOW) : start]
    return any(n in window for n in NEGATIONS)


def _affirmative_hits(text: str, patterns: list[re.Pattern]) -> list[str]:
    return [m.group() for p in patterns for m in p.finditer(text) if not _negated(text, m.start())]


def mentioned_products(text: str) -> set[str]:
    """回答中提到的目录产品（按代码或完整名称匹配）。"""
    compact = text.replace(" ", "")
    return {
        p.code
        for p in load_catalog().products
        if p.code in text or p.name.replace(" ", "") in compact
    }


def real_institutions(text: str) -> list[str]:
    return [name for name in REAL_INSTITUTIONS if name in text]


CITATION_RE = re.compile(r"\[(K\d{2}|[A-Z]{2}-[A-Z]\d{2}#[^\]\s]+)\]")


def fake_citations(reply: str, retrieved: Collection[str]) -> list[str]:
    return [cid for cid in CITATION_RE.findall(reply) if cid not in retrieved]


def check_output(
    reply: str,
    permission: Permission,
    grounding: str = "",
    retrieved: Collection[str] = (),
) -> list[str]:
    """返回违规代码列表；空列表表示通过。

    grounding 是本轮之前已出现的内容：测评前只含客户消息；测评后含客户消息、历史回答和工具结果。
    回答中提到的产品必须在其中出现过，防止模型凭空编造或测评前泄露产品信息。
    retrieved 是本轮检索到的资料编号：回答中的 [编号] 必须在其中，否则视为编造出处。
    """
    violations = []
    if _affirmative_hits(reply, PROHIBITED_CLAIMS):
        violations.append("O-PROHIBITED_CLAIM")
    ungrounded = mentioned_products(reply) - mentioned_products(grounding)
    if permission is Permission.ASSESSMENT_REQUIRED:
        if _affirmative_hits(reply, RECOMMENDATION) or ungrounded:
            violations.append("O-PERMISSION_LEAK")
    else:
        if ungrounded:
            violations.append("O-UNGROUNDED_PRODUCT")
        if _affirmative_hits(reply, PERSONALIZED):
            violations.append("O-PERSONALIZED_ADVICE")
    if steers_reassessment(reply):
        violations.append("O-REASSESSMENT_STEERING")
    if _affirmative_hits(reply, FALSE_HANDOFF):
        violations.append("O-FALSE_HANDOFF_CLAIM")
    if real_institutions(reply):
        violations.append("O-REAL_INSTITUTION")
    if fake_citations(reply, retrieved):
        violations.append("O-FAKE_CITATION")
    return violations


def describe(violations: list[str], reply: str) -> str:
    """给 LLM 的改写反馈。"""
    hits = _affirmative_hits(reply, PROHIBITED_CLAIMS) + _affirmative_hits(reply, RECOMMENDATION)
    return (
        "你的上一条回答未通过合规审查（"
        + "、".join(violations)
        + f"），问题表述：{'、'.join(dict.fromkeys(hits))}。"
        + (
            f"提到了真实机构：{'、'.join(real_institutions(reply))}。"
            if real_institutions(reply)
            else ""
        )
        + ("引用了未检索到的资料编号。" if "O-FAKE_CITATION" in violations else "")
        + (
            "人工服务尚未接入，只能说「已生成请求，待您确认」或「已提交，等待理财经理接单」。"
            if "O-FALSE_HANDOFF_CLAIM" in violations
            else ""
        )
        + (
            "不得为达到收益目标建议客户重新测评或提高风险等级；只有客户自身情况变化时才可提示重新测评。"
            if "O-REASSESSMENT_STEERING" in violations
            else ""
        )
        + (
            "不得使用「适合您」「建议配置/推荐购买」等个性化推荐措辞，可改为「在您的风险等级范围内的产品包括」。"
            if "O-PERSONALIZED_ADVICE" in violations
            else ""
        )
        + "请改写：不得承诺收益或保本；客户未完成风险测评时不得推荐或介绍任何产品；"
        "产品信息只能来自工具结果；不得提及真实机构的产品。只输出改写后的回答。"
    )
