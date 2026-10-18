"""输出审查：回答发出前的确定性检查，不调用 LLM。

规则针对**肯定句式**：「理财产品不保本」是合法的事实陈述，「保证收益」才是违规承诺。
"""

import re
from collections.abc import Collection
from decimal import Decimal

from app.assessment.scoring import rating_allows
from app.compliance.policy import Permission
from app.products.catalog import load_catalog

# 命中词所在分句中、位于其之前出现否定词，视为否定陈述，不算违规。
# 中文否定词常与被否定的词相隔较远（「没有任何一款理财产品是保本保收益的」），
# 因此看整个分句，最多 20 字。
NEGATIONS = (
    "不",
    "非",
    "没有",
    "无法",
    "不能",
    "不会",
    "并非",
    "绝非",
    "未",
    "无任何",
    "禁止",
    "杜绝",
)
NOT_NEGATION = re.compile(r"不仅|不但|不只|不光|毫不|无不|不可思议")  # 含「不」但不表示否定
CLAUSE_BREAK = re.compile(r"[，,。！？；;：:\n]")
NEGATION_WINDOW = 20

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
REASSESSMENT = re.compile(
    r"重新(完成|进行|做)?(一次)?(风险)?(承受能力)?(测评|评估)"
    r"|调(整|高).{0,4}(评级|风险等级)|提高.{0,4}风险承受"
)
# 与重新测评同句出现即构成诱导：收益、更高风险，或把测评当作「解锁」更高等级产品的途径
RISK_OR_RETURN = re.compile(
    r"收益|更高(的)?风险|高风险|PR[3-5]|波动|权益类|相应等级|更高(的)?(风险)?等级"
)
# 另一种说法：建议（经由理财经理）评估是否需要更高的风险等级
RISK_UPGRADE = re.compile(r"(更高|提高|调高|提升)(的)?.{0,2}(风险等级|评级|风险承受)")
SUGGESTION = re.compile(r"建议|可以|可|考虑|评估|是否需要|如需|若需")
# 同一句明确说明了限制（与风险等级不匹配、超出评级），是在解释取舍，而不是建议调高评级
LIMITATION = re.compile(r"不匹配|超出|不符合|无法购买|不能购买|无权")
SENTENCE_SPLIT = re.compile(r"[。！？；\n]")
# 需求匹配式推荐（产品负责人决定，2026-10-18）：允许在评级范围内推荐，以下三类仍然禁止
RECOMMEND_WORDS = re.compile(r"推荐|建议|适合|匹配|首选|可以考虑|值得|不妨")
NOT_RECOMMENDING = re.compile(r"不(作|做)?(推荐|建议)|无法推荐|不能推荐|不适合")
# 1. 推荐超出客户评级的产品
# 2. 制造紧迫感的销售话术
PRESSURE_SALES = [
    re.compile(p)
    for p in (
        r"限时",
        r"抢购",
        r"(名额|额度)(有限|紧张)",
        r"仅剩",
        r"售完即止",
        r"错过(就|再|将|了)",
        r"最后(的)?(机会|一天|几天)",
        r"赶紧|赶快",
        r"抓紧(时间)?(购买|买入|下单|入手)",
        r"马上(购买|下单|买入|抢)",
        r"手慢无",
        r"再不买",
    )
]
# 4. 把礼品、积分、返现与购买某款产品挂钩（权益只与资产总额挂钩，见 data/benefits/benefits.yaml）
GIFT_FOR_PURCHASE = [
    re.compile(p)
    for p in (
        r"(购买|买入|认购|申购)[^。！？；\n]{0,15}(送|赠送|返现|返利|礼品|积分)",
        r"(送|赠送|返现|返利)[^。！？；\n]{0,10}(购买|买入|认购|申购)",
    )
]
# 3. 以收益高低作为推荐理由
RETURN_PITCH = [
    re.compile(p)
    for p in (
        r"(推荐|首选|建议|值得|不妨).{0,12}收益(最高|更高|最好)",
        r"收益(最高|更高|最好).{0,12}(推荐|首选|值得|建议)",
    )
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


# 跨口径比较收益：业绩比较基准与七日年化（现金管理类）口径不同，不能比较高低。
# 对比表由工具分列口径；这条规则拦截回答文字中的比较（P7 场景评估 P05 发现，Prompt 约束不可靠）
BENCHMARK = re.compile(r"业绩比较基准")
CASH_METRIC = re.compile(r"七日年化|万份收益|现金管理类|活钱宝|日日盈")
COMPARISON = re.compile(r"高于|低于|更高|更低|略高|略低|稍高|稍低|高一些|低一些|超过|不如|高出")
METRIC_CAVEAT = re.compile(r"口径不同|不同口径|(不能|不可|无法|不宜)直接比较")


def metric_mixing(text: str) -> list[str]:
    """同句比较，或同一段落中先提现金管理类、再说某产品「业绩比较基准更高」（场景评估 P05）。"""
    hits = []
    for para in PARAGRAPH_SPLIT.split(text):
        cash_in_para = bool(CASH_METRIC.search(para))
        hits += [
            s.strip()[:40]
            for s in SENTENCE_SPLIT.split(para)
            if BENCHMARK.search(s)
            and COMPARISON.search(s)
            and (CASH_METRIC.search(s) or cash_in_para)
            and not METRIC_CAVEAT.search(s)
        ]
    return hits


# 收益数字必须有来源：业绩比较基准、七日年化所在句中的百分数，须出现在本轮工具结果或此前对话中。
# P7 场景评估 N02 发现模型把新品的业绩比较基准 2.80%–3.30% 说成 2.60%–3.20%。
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# 只检查紧跟在收益指标名称后的数字（含区间），不检查同句中的配置占比等其他百分数（场景评估 V02）
METRIC_FIGURE = re.compile(
    r"(?:业绩比较基准|七日年化(?:收益率)?|万份收益)[^。；！？\n%\d]{0,12}"
    r"(\d+(?:\.\d+)?)\s*%(?:\s*[–—\-~至到]\s*(\d+(?:\.\d+)?)\s*%)?"
)


def ungrounded_figures(text: str, grounding: str) -> list[str]:
    known = {Decimal(m) for m in PERCENT.findall(grounding)}
    figures = [n for m in METRIC_FIGURE.finditer(text) for n in m.groups() if n]
    return [f"{n}%" for n in figures if Decimal(n) not in known]


def unsuitable_recommendations(text: str, risk_rating: str | None) -> list[str]:
    """推荐了超出客户评级的产品的句子（同句说明「超出 / 不推荐」等限制的不算）。"""
    if not risk_rating:
        return []
    catalog = load_catalog()
    hits = []
    for s in SENTENCE_SPLIT.split(text):
        if not RECOMMEND_WORDS.search(s) or LIMITATION.search(s) or NOT_RECOMMENDING.search(s):
            continue
        for code in mentioned_products(s):
            product = catalog.get(code)
            if product and not rating_allows(risk_rating, product.effective_risk_level):
                hits.append(s.strip()[:40])
                break
    return hits


PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def _sentence_steers(s: str) -> bool:
    return bool(
        (REASSESSMENT.search(s) and RISK_OR_RETURN.search(s))
        or (RISK_UPGRADE.search(s) and SUGGESTION.search(s) and not LIMITATION.search(s))
    )


def _paragraph_steers(p: str) -> bool:
    # 同一段先讲「5% 需要 PR3 以上」，下一句再说「情况变化可以重新测评」，连起来读就是诱导
    # （P7 场景评估 M01 发现）。讨论收益或更高风险时，不主动提重新测评。
    return bool(REASSESSMENT.search(p) and RISK_OR_RETURN.search(p))


def steers_reassessment(text: str) -> bool:
    return any(_sentence_steers(s) for s in SENTENCE_SPLIT.split(text)) or any(
        _paragraph_steers(p) for p in PARAGRAPH_SPLIT.split(text)
    )


# 客户直接问「哪款保本 / 保收益」时，回答必须明确否定。
# 模型有时只说「基准不是承诺」「存款保本」而回避正面回答，容易让客户误以为低风险理财也保本，
# 因此由代码补充标准说明（P7 场景评估 S02 发现）
GUARANTEE_QUESTION = re.compile(r"保本|保收益|保证收益|稳赚|零风险|无风险|不会亏|不亏")
GUARANTEE_DENIED = re.compile(r"不保本|不保证本金|不承诺(保本|收益)|不保证收益|没有.{0,6}保本")
NO_GUARANTEE_NOTE = (
    "银行理财产品不保本、不承诺收益，包括低风险的现金管理类产品，均存在本金亏损的可能。"
)


def needs_no_guarantee_note(question: str, reply: str) -> bool:
    return bool(GUARANTEE_QUESTION.search(question)) and not GUARANTEE_DENIED.search(reply)


def remove_steering(reply: str) -> str:
    """删去诱导调高评级的句子。这类句子是附加建议，删去后回答的其余内容仍然完整。

    段落级诱导只删去该段中提到重新测评的句子，保留对收益与风险取舍的说明。
    """
    paragraphs = re.split(f"({PARAGRAPH_SPLIT.pattern})", reply)
    out = []
    for i, para in enumerate(paragraphs):
        if i % 2:  # 段落分隔符
            out.append(para)
            continue
        drop_reassessment = _paragraph_steers(para)
        parts = re.split(f"({SENTENCE_SPLIT.pattern})", para)
        out.append(
            "".join(
                s + d
                for s, d in zip(parts[::2], [*parts[1::2], ""], strict=True)
                if not _sentence_steers(s) and not (drop_reassessment and REASSESSMENT.search(s))
            )
        )
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - NEGATION_WINDOW) : start]
    breaks = list(CLAUSE_BREAK.finditer(window))
    clause = window[breaks[-1].end() :] if breaks else window
    clause = NOT_NEGATION.sub("", clause)
    return any(n in clause for n in NEGATIONS)


# 引号内的表述若出现在提醒、警示语境中（如：销售说「保本」属于违规宣传），是引述而非承诺
QUOTED = re.compile(r"[「『“\"‘'][^」』”\"’']{1,20}[」』”\"’']")
WARNING_CONTEXT = re.compile(
    r"违规|不应|不要|不能|不得|禁止|警惕|谨慎|虚假|误导|所谓|别信|不可信|不实"
)


def _quoted_warning(text: str, start: int, end: int) -> bool:
    for q in QUOTED.finditer(text):
        if q.start() <= start and end <= q.end():
            left = max(text.rfind(c, 0, start) for c in "。！？；\n")
            right = min([i for c in "。！？；\n" if (i := text.find(c, end)) != -1] or [len(text)])
            return bool(WARNING_CONTEXT.search(text[left + 1 : right]))
    return False


def _affirmative_hits(text: str, patterns: list[re.Pattern]) -> list[str]:
    return [
        m.group()
        for p in patterns
        for m in p.finditer(text)
        if not _negated(text, m.start()) and not _quoted_warning(text, m.start(), m.end())
    ]


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
    risk_rating: str | None = None,
) -> list[str]:
    """返回违规代码列表；空列表表示通过。

    grounding 是本轮之前已出现的内容：测评前只含客户消息；测评后含客户消息、历史回答和工具结果。
    回答中提到的产品必须在其中出现过，防止模型凭空编造或测评前泄露产品信息。
    retrieved 是本轮检索到的资料编号：回答中的 [编号] 必须在其中，否则视为编造出处。
    risk_rating 是客户的有效评级：用于检查是否推荐了超出评级的产品。
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
        if unsuitable_recommendations(reply, risk_rating):
            violations.append("O-UNSUITABLE_RECOMMENDATION")
    if _affirmative_hits(reply, PRESSURE_SALES):
        violations.append("O-PRESSURE_SALES")
    if _affirmative_hits(reply, RETURN_PITCH):
        violations.append("O-RETURN_PITCH")
    if metric_mixing(reply):
        violations.append("O-METRIC_MIXING")
    if _affirmative_hits(reply, GIFT_FOR_PURCHASE):
        violations.append("O-GIFT_FOR_PURCHASE")
    if permission is Permission.ASSESSED and ungrounded_figures(reply, grounding):
        violations.append("O-UNGROUNDED_FIGURE")
    if steers_reassessment(reply):
        violations.append("O-REASSESSMENT_STEERING")
    if _affirmative_hits(reply, FALSE_HANDOFF):
        violations.append("O-FALSE_HANDOFF_CLAIM")
    if real_institutions(reply):
        violations.append("O-REAL_INSTITUTION")
    if fake_citations(reply, retrieved):
        violations.append("O-FAKE_CITATION")
    return violations


def offending_snippets(
    reply: str, risk_rating: str | None = None, grounding: str | None = None
) -> list[str]:
    """违规片段（写入审计记录，便于事后定位模型反复触发的表述）。"""
    hits = _affirmative_hits(reply, PROHIBITED_CLAIMS) + _affirmative_hits(reply, PRESSURE_SALES)
    hits += _affirmative_hits(reply, RETURN_PITCH) + _affirmative_hits(reply, FALSE_HANDOFF)
    hits += metric_mixing(reply) + _affirmative_hits(reply, GIFT_FOR_PURCHASE)
    if grounding is not None:
        hits += [
            f"产品:{c}" for c in sorted(mentioned_products(reply) - mentioned_products(grounding))
        ]
    if grounding is not None:
        hits += ungrounded_figures(reply, grounding)
    # 测评前任何推荐都是违规；测评后只有推荐超评级产品才是
    hits += unsuitable_recommendations(reply, risk_rating) if risk_rating else []
    hits += _affirmative_hits(reply, RECOMMENDATION) if not risk_rating else []
    hits += [s.strip()[:40] for s in SENTENCE_SPLIT.split(reply) if _sentence_steers(s)]
    hits += [
        s.strip()[:40]
        for p in PARAGRAPH_SPLIT.split(reply)
        if _paragraph_steers(p)
        for s in SENTENCE_SPLIT.split(p)
        if REASSESSMENT.search(s)
    ]
    return list(dict.fromkeys(hits))[:5]


def describe(
    violations: list[str], reply: str, risk_rating: str | None = None, grounding: str | None = None
) -> str:
    """给 LLM 的改写反馈。"""
    hits = _affirmative_hits(reply, PROHIBITED_CLAIMS) + _affirmative_hits(reply, RECOMMENDATION)
    hits += offending_snippets(reply, risk_rating, grounding)
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
            "理财经理尚未接入，只能说「已将您的咨询要点同步给理财经理，您可以通过名片直接联系」。"
            if "O-FALSE_HANDOFF_CLAIM" in violations
            else ""
        )
        + (
            "不得为达到收益目标或了解更高等级产品而建议客户重新测评或提高风险等级，"
            "请删去相关句子；只有客户自身情况变化时才可提示重新测评。"
            if "O-REASSESSMENT_STEERING" in violations
            else ""
        )
        + (
            "不得推荐超出客户风险等级的产品；如提到这类产品，必须说明超出风险等级、无法购买。"
            if "O-UNSUITABLE_RECOMMENDATION" in violations
            else ""
        )
        + (
            "不得使用「限时」「错过就没了」「赶紧买」等制造紧迫感的话术，尊重客户自己的决定。"
            if "O-PRESSURE_SALES" in violations
            else ""
        )
        + (
            "推荐理由只能是期限、流动性、费用、起购金额等与客户需求的匹配点，不能以收益高低作为理由。"
            if "O-RETURN_PITCH" in violations
            else ""
        )
        + (
            "回答中的业绩比较基准或七日年化数字与产品资料不符或没有来源，"
            "只能使用工具结果中的原始数字，不确定时不要写具体数字。"
            if "O-UNGROUNDED_FIGURE" in violations
            else ""
        )
        + (
            "权益和活动只与金融资产总额挂钩（存款也计入），不能说购买某款产品送礼品、积分或返现。"
            if "O-GIFT_FOR_PURCHASE" in violations
            else ""
        )
        + (
            "业绩比较基准与七日年化（现金管理类）口径不同，不能比较高低；"
            "请删去比较，用期限、流动性、费用说明区别。"
            if "O-METRIC_MIXING" in violations
            else ""
        )
        + "请改写：不得承诺收益或保本；客户未完成风险测评时不得推荐或介绍任何产品；"
        "产品信息只能来自工具结果；不得提及真实机构的产品。只输出改写后的回答。"
    )
