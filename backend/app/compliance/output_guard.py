"""输出审查：回答发出前的确定性检查，不调用 LLM。

规则针对**肯定句式**：「理财产品不保本」是合法的事实陈述，「保证收益」才是违规承诺。

英文界面（P8-2b）：每条规则都有英文版（*_EN）。中文界面只用中文规则（行为与之前完全一致）；
英文界面中英文规则同时生效——模型在英文回答里夹带中文表述时同样会被拦截。
"""

import re
from collections.abc import Collection
from decimal import Decimal
from functools import lru_cache

from app.assessment.scoring import rating_allows
from app.compliance.policy import Permission
from app.core.i18n import is_en, register
from app.knowledge.kb import KB_PATH
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
# 英文否定词与被否定的词通常相隔更多字符（"we can't promise you any guaranteed returns"）
# 转述他人说法（"any product claiming…"、"if anyone tells you…"）与否定同样处理：不是 AI 自己的承诺
NEGATIONS_EN = re.compile(
    r"\b(not|no|never|cannot|without|neither|nor|nothing|none|nobody|avoid|instead of|"
    r"claim(s|ing|ed)?|anyone|someone|beware|wary|so-called|marketed as|advertis\w*|"
    r"watch out|be careful|red flag)\b|n't\b",
    re.I,
)
NOT_NEGATION_EN = re.compile(r"\bnot only\b|\bno doubt\b|\bno matter\b", re.I)
# 场景评估发现：「regulations do not allow me to sell you a product with a guaranteed return」
# 否定词与关键词相隔 60 字符以上，英文窗口取 100 字符（约 15–20 个词），仍以分句为界
NEGATION_WINDOW_EN = 100
# 英文常把否定放在主语之后（场景评估 S02）：「Principal-protected bank products no longer exist」
# 「principal-protected products with guaranteed returns are no longer issued」
POST_NEGATION_EN = re.compile(
    r"\b(no longer|don't exist|do not exist|doesn't exist|does not exist|"
    r"(are|is)n't (available|offered|allowed|permitted|issued|sold)|"
    r"(are|is) not (available|offered|allowed|permitted|issued|sold)|"
    r"(have|has) been (phased out|abolished|banned|eliminated)|(are|is) (prohibited|banned))\b",
    re.I,
)
POST_NEGATION_WINDOW_EN = 80
# 同一句明确是警示语境（无引号也算）：转述的说法被定性为违规、误导
WARNING_SENTENCE_EN = re.compile(
    r"misleading|non-?compliant|not compl(y|iant)|violat\w*|illegal|prohibited|"
    r"not (being )?truthful|red flag|scam|fraud\w*|false claim",
    re.I,
)
# 英文分句：句末标点后须有空白，避免把小数点（2.5%）当作句末
SENTENCE_SPLIT_EN = r"(?<=[.!?;])\s+"


def _rules(zh: list[re.Pattern], en: list[re.Pattern]) -> list[re.Pattern]:
    """当前语言下生效的规则：中文界面只用中文规则，英文界面中英文同时生效。"""
    return zh + en if is_en() else zh


def _any(zh: re.Pattern, en: re.Pattern, text: str) -> bool:
    return bool(zh.search(text) or (is_en() and en.search(text)))


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
_RETURN_WORDS = r"(returns?|principal|profits?|income|yields?|gains?|payouts?)"
PROHIBITED_CLAIMS_EN = [
    re.compile(p, re.I)
    for p in (
        rf"\bguarantee[sd]?\b[^.;!?\n]{{0,25}}\b{_RETURN_WORDS}\b",
        rf"\b{_RETURN_WORDS}\b[^.;!?\n]{{0,20}}\b(is|are|will be|stays?)\s+(fully\s+)?guaranteed",
        r"(?<!non-)(?<!non )\bprincipal[- ](protected|guaranteed)\b",
        r"(?<!non-)\b(risk[- ]free|zero[- ]risk)\b",
        # 只拦「there's / it carries no risk」这类断言；
        # 「capital preservation with no risk」描述的是客户目标，不算
        r"\b(there'?s|there is|it'?s|carries|carry|has|have|involves?)\s+"
        r"(virtually\s+|basically\s+|almost\s+|absolutely\s+)?no risk\b(?!-)",
        r"\b(can't|cannot|won't|will not|never) lose\b",
        r"\b(sure|surefire|safe) (bet|thing|win)\b",
        r"\b(definitely|certainly|surely|absolutely)\s+(will\s+|can\s+)?"
        r"(earn|make money|reach|achieve|double|profit|beat)",
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
RECOMMENDATION_EN = [
    re.compile(p, re.I)
    for p in (
        r"\b(recommend|suggest)\b[^.;!?\n]{0,15}\b(buy|buying|invest|investing|choose|choosing|"
        r"go with|put (your|the) money)",
        # 与中文「适合您的产品是 / 有」一致：要有断言动词。
        # 「完成测评后，我可以为您筛选 suitable products for you」是邀请测评，不算推荐（评估 R03）
        r"\b(suitable|right|best) (product|option|choice)s? for you\s+(is|are|would be|include)\b",
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
# 真实理财公司的英文名称（含常见缩写写法）
REAL_INSTITUTIONS_EN = re.compile(
    r"\b(ICBC|CCB|ABC|BOC|BoCom|Bank of Communications|PSBC|Postal Savings|CMB|China Merchants|"
    r"CIB|Industrial Bank|CITIC|Everbright|Ping ?An|Hua ?Xia|SPDB|Minsheng|CGB|China Guangfa|"
    r"Bohai|Hengfeng|Ningbo|Hangzhou|Huishang|Nanjing|Qingdao|Jiangsu|Bank of Shanghai|"
    r"Bank of Beijing|Chongqing Rural)\s+(Bank\s+)?Wealth\b"
    r"|\b(BlackRock CCB|Schroders? BoCom|Goldman Sachs ICBC|Amundi BOC)\b",
    re.I,
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
# 英文：retake / redo the profile、reassess；
# 「complete your risk profile」是给未测评客户的正常提示，不算
REASSESSMENT_EN = re.compile(
    r"\b(re-?take|redo|re-do|repeat|re-?run)\b[^.;!?\n]{0,25}\b(profile|assessment|questionnaire)\b"
    r"|\b(profile|assessment|questionnaire)\s+again\b|\breassess(ment|ing|ed)?\b"
    r"|\b(raise|increase|upgrade|bump up|adjust)\s+(your\s+)?(risk\s+)?(rating|tolerance)\b",
    re.I,
)
RISK_OR_RETURN_EN = re.compile(
    r"\breturns?\b|\byields?\b|higher[- ]risk|\bPR[3-5]\b|volatil|\bequit(y|ies)\b"
    r"|higher (risk )?(level|rating|tier)s?|\btarget\b",
    re.I,
)
RISK_UPGRADE_EN = re.compile(
    r"\b(higher|raise|raising|increase|increasing|upgrade|upgrading)\b[^.;!?\n]{0,15}"
    r"\b(risk (rating|level|tolerance)|rating)\b",
    re.I,
)
SUGGESTION_EN = re.compile(
    r"\b(suggest|recommend|could|can|consider|might|may want|if you'd like|whether|option)\b", re.I
)
LIMITATION_EN = re.compile(
    r"\b(above|exceeds?|beyond|outside|not eligible|isn't eligible|ineligible|can't buy|"
    r"cannot buy|not allowed|doesn't match|don't match|not suitable)\b",
    re.I,
)
SENTENCE_SPLIT_ANY = re.compile(f"[。！？；\\n]|{SENTENCE_SPLIT_EN}")


def _sentences(text: str) -> list[str]:
    return (SENTENCE_SPLIT_ANY if is_en() else SENTENCE_SPLIT).split(text)


# 需求匹配式推荐（产品负责人决定，2026-10-18）：允许在评级范围内推荐，以下三类仍然禁止
RECOMMEND_WORDS = re.compile(r"推荐|建议|适合|匹配|首选|可以考虑|值得|不妨")
NOT_RECOMMENDING = re.compile(r"不(作|做)?(推荐|建议)|无法推荐|不能推荐|不适合")
RECOMMEND_WORDS_EN = re.compile(
    r"\b(recommend|suggest|suitable|good fit|fits?|match(es|ed)?|top pick|worth considering|"
    r"consider|go with)\b",
    re.I,
)
NOT_RECOMMENDING_EN = re.compile(
    r"\b(not|don't|can't|cannot|wouldn't|won't)\s+(recommend|suggest)"
    r"|\bnot (a )?(suitable|good fit)"
    r"|\bunsuitable\b",
    re.I,
)
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
PRESSURE_SALES_EN = [
    re.compile(p, re.I)
    for p in (
        r"\blimited[- ]time\b",
        r"\bact (now|fast|quickly|today)\b",
        r"\bdon'?t miss (out|this|it)\b",
        r"\bonly\s+(\w+\s+){1,2}(left|remaining)\b",
        r"\b(last|final) chance\b",
        r"\bhurry\b",
        r"\bbefore it'?s (gone|too late|sold out)\b",
        r"\bsell(s|ing)? out fast\b",
        r"\b(spots|quota|slots|allocation) (is |are )?(limited|running out)\b",
        r"\bwhile (it|they|supplies|stocks?) lasts?\b",
        r"\b(buy|grab|lock (it|this) in|snap (it|this) up)\s+(it\s+)?"
        r"(now|today|right away|immediately)\b",
        r"\bnow or never\b",
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
_GIFT = r"(gifts?|bonus points|points|cash ?back|rebates?|rewards?|free)"
GIFT_FOR_PURCHASE_EN = [
    re.compile(p, re.I)
    for p in (
        rf"\b(buy|buying|purchase|purchasing|subscribe|subscribing)\b[^.;!?\n]{{0,30}}"
        rf"\b(get|earn|receive|comes? with)s?\b[^.;!?\n]{{0,15}}\b{_GIFT}\b",
        rf"\b{_GIFT}\b[^.;!?\n]{{0,25}}\b(when|if|for)\s+(you\s+)?(buy|purchase|subscribe)",
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
_HIGH_RETURN = r"(highest|higher|best|top|biggest|bigger)\s+(returns?|yields?|benchmark|upside)"
RETURN_PITCH_EN = [
    re.compile(p, re.I)
    for p in (
        rf"\b(recommend|top pick|best choice|go with|worth considering|suggest)\b[^;!?\n]{{0,60}}"
        rf"\b{_HIGH_RETURN}\b",
        rf"\b{_HIGH_RETURN}\b[^;!?\n]{{0,40}}\b(recommend|top pick|best choice|worth|suggest)",
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
_STAFF = r"(relationship manager|RM|advisor|adviser|agent|banker|human|manager)"
FALSE_HANDOFF_EN = [
    re.compile(p, re.I)
    for p in (
        r"\b(I've|I have|we've|we have)\s+(now\s+)?(connected|transferred|put)\s+you\b",
        rf"\b(I've|I have|we've|we have)\s+(now\s+)?(contacted|notified|reached|called)\b"
        rf"[^.;!?\n]{{0,20}}\b{_STAFF}\b",
        rf"\b{_STAFF}\b[^.;!?\n]{{0,20}}\b(is|has)\s+(now\s+)?(joined|online|connected|on the line|"
        r"handling your|taking care of|serving you|reached out|contacted you|been notified)",
    )
]


# 宣称已完成实际并未发生的操作（场景评估 N02 发现：模型说「已为您预约开售提醒」，但没有调用工具）。
# 提醒：只有本轮工具结果或客户资料中的提醒记录里有「已预约开售提醒」时才能这样说；
# 买入：AI 无法代客户买入，任何「已为您买入」都不属实。
REMINDER_EVIDENCE = ("已预约开售提醒", "Sale reminder set")
REMINDER_CLAIM = [
    re.compile(p)
    for p in (
        r"(已|已经)(为您|帮您)?(预约|设置|设好|开启|订阅)(了|好)?[^。！？\n]{0,40}提醒",
        r"提醒(已|已经)(设置|预约|设好|开启)",
    )
]
REMINDER_CLAIM_EN = [
    re.compile(p, re.I)
    for p in (
        r"\b(I've|I have|we've|we have)\s+(now\s+)?(set|scheduled|booked|added|turned on|created)\b"
        r"[^.;!?\n]{0,40}\breminder",
        r"\breminder\b[^.;!?\n]{0,30}\b(is|has been)\s+(now\s+)?"
        r"(set|scheduled|booked|on|created)\b",
    )
]
PURCHASE_CLAIM = [
    re.compile(p)
    for p in (
        r"(已|已经)(为您|帮您|替您)(买入|购买|下单|申购|认购)",
        r"(已|已经)(为您|帮您)?锁定.{0,4}(额度|份额)",
    )
]
PURCHASE_CLAIM_EN = [
    re.compile(p, re.I)
    for p in (
        r"\b(I've|I have|we've|we have)\s+(now\s+)?(bought|purchased|placed (an |the |your )?order|"
        r"subscribed you|locked in)",
    )
]


def false_action_claims(reply: str, grounding: str) -> list[str]:
    hits = _affirmative_hits(reply, _rules(PURCHASE_CLAIM, PURCHASE_CLAIM_EN))
    if not any(e in grounding for e in REMINDER_EVIDENCE):
        hits += _affirmative_hits(reply, _rules(REMINDER_CLAIM, REMINDER_CLAIM_EN))
    return hits


# 软性收益比较（P8-2b 场景评估 P05，中英文都出现）：没有出现「业绩比较基准」字样，
# 但在推荐 / 分配语境中以收益更高为理由，如「另一部分放在稳享每日开放争取稍高一些的收益空间」
# 「This is the highest-yielding option」。同句在讲风险取舍（更高收益意味着更高风险）的不算。
SOFT_RETURN = re.compile(
    r"(稍|略|更)高(一些|一点)?的收益|收益空间|收益(更|稍|略)高|收益(更有|占)优势"
)
SOFT_RETURN_EN = re.compile(
    r"\b(highest|higher|better)[- ]yielding\b|\b(higher|better|more|extra|bigger|highest|best)\s+"
    r"(returns?|yields?|upside|income)\b|\b(return|yield) (edge|advantage|pickup)\b"
    r"|\bmore (return|upside|yield) potential\b",
    re.I,
)
PICK = re.compile(r"放在|配置|选择|建议|推荐|考虑|适合|首选|买入|购买")
PICK_EN = re.compile(
    r"\b(option|pick|choice|put|allocate|recommend|suggest|consider|go with|place|park|buy|"
    r"highlight|focus on|lean toward)\b",
    re.I,
)
TRADEOFF = re.compile(r"风险|波动|不是预期|不代表|不保证|难以兼得|代价|意味着|亏损")
TRADEOFF_EN = re.compile(
    r"\brisk|volatil|fluctuat|\bloss|not (an? )?(expected|guarantee)|trade-?off|in exchange"
    r"|comes? with|\bmeans?\b|not a promise",
    re.I,
)


def soft_return_pitch(text: str) -> list[str]:
    hits = []
    for s in _sentences(text):
        for pattern in [SOFT_RETURN, SOFT_RETURN_EN] if is_en() else [SOFT_RETURN]:
            m = pattern.search(s)
            if (
                m
                and _any(PICK, PICK_EN, s)
                and not _any(TRADEOFF, TRADEOFF_EN, s)
                and not _negated(s, m.start())
            ):
                hits.append(s.strip()[:60])
                break
    return hits


# 跨口径比较收益：业绩比较基准与七日年化（现金管理类）口径不同，不能比较高低。
# 对比表由工具分列口径；这条规则拦截回答文字中的比较（P7 场景评估 P05 发现，Prompt 约束不可靠）
BENCHMARK = re.compile(r"业绩比较基准")
CASH_METRIC = re.compile(r"七日年化|万份收益|现金管理类|活钱宝|日日盈")
COMPARISON = re.compile(r"高于|低于|更高|更低|略高|略低|稍高|稍低|高一些|低一些|超过|不如|高出")
METRIC_CAVEAT = re.compile(r"口径不同|不同口径|(不能|不可|无法|不宜)直接比较")
BENCHMARK_EN = re.compile(r"\bbenchmark", re.I)
CASH_METRIC_EN = re.compile(
    r"7-day|seven-day|income per 10,000|cash management|Ready Cash|Daily Gain", re.I
)
COMPARISON_EN = re.compile(
    r"\b(higher|lower|more than|less than|exceeds?|beats?|above|below|better|worse|outperforms?|"
    r"edges? out|tops)\b",
    re.I,
)
METRIC_CAVEAT_EN = re.compile(
    r"different (measures?|metrics?|bases|basis|kinds?)"
    r"|(can't|cannot|shouldn't|can not) be compared"
    r"|not (directly )?comparable|(aren't|isn't) (directly )?comparable|apples",
    re.I,
)


def metric_mixing(text: str) -> list[str]:
    """同句比较，或同一段落中先提现金管理类、再说某产品「业绩比较基准更高」（场景评估 P05）。"""
    hits = []
    for para in PARAGRAPH_SPLIT.split(text):
        cash_in_para = _any(CASH_METRIC, CASH_METRIC_EN, para)
        hits += [
            s.strip()[:40]
            for s in _sentences(para)
            if _any(BENCHMARK, BENCHMARK_EN, s)
            and _any(COMPARISON, COMPARISON_EN, s)
            and (_any(CASH_METRIC, CASH_METRIC_EN, s) or cash_in_para)
            and not _any(METRIC_CAVEAT, METRIC_CAVEAT_EN, s)
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
METRIC_FIGURE_EN = re.compile(
    r"(?:benchmark|7-day (?:annualized )?yield|seven-day (?:annualized )?yield)[^;!?\n%\d]{0,20}"
    r"(\d+(?:\.\d+)?)\s*%(?:\s*(?:[–—\-~]|to)\s*(\d+(?:\.\d+)?)\s*%)?",
    re.I,
)


def ungrounded_figures(text: str, grounding: str) -> list[str]:
    known = {Decimal(m) for m in PERCENT.findall(grounding)}
    patterns = [METRIC_FIGURE, METRIC_FIGURE_EN] if is_en() else [METRIC_FIGURE]
    figures = [n for p in patterns for m in p.finditer(text) for n in m.groups() if n]
    return [f"{n}%" for n in figures if Decimal(n) not in known]


# 金额必须有来源（P8-4）：回答中的人民币金额须出现在工具结果、客户资料或客户自己说过的话里。
# 「金额计算一律用代码」是不可违反的规则，P8-2b 场景评估发现模型偶尔自己算「到手金额」并算错
# （10 万元赎回费 500 元，模型写成到手 95,500 元）。
# 允许 0.1% 的四舍五入差异（162.89 万 ≈ 1,628,894.63，误差 0.0003%）。
# 曾用 0.5%：英文评估中模型把到手 99,500 写成 995,000，与 1,000,000 恰好相差 0.5% 而漏拦。
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
AMOUNT_ZH = re.compile(_NUM + r"\s*(亿元|亿|万元|万(?!份)|元)")
AMOUNT_YEN = re.compile(r"[¥￥]\s*" + _NUM + r"(?:\s*(万|亿|million|billion|[kK])\b)?")
AMOUNT_EN = re.compile(_NUM + r"\s*(million|billion)?\s*(?:yuan|CNY|RMB)\b", re.I)
BARE_NUMBER = re.compile(_NUM)
UNIT = {
    "亿元": 10**8,
    "亿": 10**8,
    "万元": 10**4,
    "万": 10**4,
    "元": 1,
    "million": 10**6,
    "billion": 10**9,
    "k": 10**3,
    None: 1,
}
AMOUNT_TOLERANCE = Decimal("0.001")


def _to_decimal(number: str) -> Decimal | None:
    try:
        return Decimal(number.replace(",", ""))
    except ArithmeticError:
        return None


def _amounts(text: str) -> list[tuple[str, Decimal]]:
    found = []
    for pattern in (AMOUNT_ZH, AMOUNT_YEN, AMOUNT_EN):
        for m in pattern.finditer(text):
            value = _to_decimal(m.group(1))
            unit = (m.group(2) or None) if m.lastindex and m.lastindex >= 2 else None
            if value is not None:
                found.append((m.group().strip(), value * UNIT[unit.lower() if unit else None]))
    return found


@lru_cache
def _reference_amounts() -> frozenset[Decimal]:
    """知识库中的金额（已人工核对原文，如存款保险 50 万元）：模型直接引用不算编造。"""
    text = KB_PATH.read_text(encoding="utf-8")
    return frozenset(v for _, v in _amounts(text))


def ungrounded_amounts(reply: str, facts: str) -> list[str]:
    known = {v for _, v in _amounts(facts)} | _reference_amounts()
    known |= {v for n in BARE_NUMBER.findall(facts) if (v := _to_decimal(n)) is not None}
    hits = []
    for text, value in _amounts(reply):
        if value == 0:
            continue
        if not any(abs(value - k) <= max(abs(k) * AMOUNT_TOLERANCE, Decimal(1)) for k in known):
            hits.append(text)
    return list(dict.fromkeys(hits))


def unsuitable_recommendations(text: str, risk_rating: str | None) -> list[str]:
    """推荐了超出客户评级的产品的句子（同句说明「超出 / 不推荐」等限制的不算）。"""
    if not risk_rating:
        return []
    catalog = load_catalog()
    hits = []
    for s in _sentences(text):
        if (
            not _any(RECOMMEND_WORDS, RECOMMEND_WORDS_EN, s)
            or _any(LIMITATION, LIMITATION_EN, s)
            or _any(NOT_RECOMMENDING, NOT_RECOMMENDING_EN, s)
        ):
            continue
        for code in mentioned_products(s):
            product = catalog.get(code)
            if product and not rating_allows(risk_rating, product.effective_risk_level):
                hits.append(s.strip()[:40])
                break
    return hits


PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def _reassessment(s: str) -> bool:
    return _any(REASSESSMENT, REASSESSMENT_EN, s)


def _sentence_steers(s: str) -> bool:
    zh = (REASSESSMENT.search(s) and RISK_OR_RETURN.search(s)) or (
        RISK_UPGRADE.search(s) and SUGGESTION.search(s) and not LIMITATION.search(s)
    )
    if zh or not is_en():
        return bool(zh)
    return bool(
        (_reassessment(s) and _any(RISK_OR_RETURN, RISK_OR_RETURN_EN, s))
        or (
            RISK_UPGRADE_EN.search(s)
            and SUGGESTION_EN.search(s)
            and not _any(LIMITATION, LIMITATION_EN, s)
        )
    )


def _paragraph_steers(p: str) -> bool:
    # 同一段先讲「5% 需要 PR3 以上」，下一句再说「情况变化可以重新测评」，连起来读就是诱导
    # （P7 场景评估 M01 发现）。讨论收益或更高风险时，不主动提重新测评。
    return bool(_reassessment(p) and _any(RISK_OR_RETURN, RISK_OR_RETURN_EN, p))


def steers_reassessment(text: str) -> bool:
    return any(_sentence_steers(s) for s in _sentences(text)) or any(
        _paragraph_steers(p) for p in PARAGRAPH_SPLIT.split(text)
    )


# 客户直接问「哪款保本 / 保收益」时，回答必须明确否定。
# 模型有时只说「基准不是承诺」「存款保本」而回避正面回答，容易让客户误以为低风险理财也保本，
# 因此由代码补充标准说明（P7 场景评估 S02 发现）
GUARANTEE_QUESTION = re.compile(r"保本|保收益|保证收益|稳赚|零风险|无风险|不会亏|不亏")
GUARANTEE_DENIED = re.compile(r"不保本|不保证本金|不承诺(保本|收益)|不保证收益|没有.{0,6}保本")
GUARANTEE_QUESTION_EN = re.compile(
    r"\bguarantee|principal[- ]protected|risk[- ]free|\bno risk\b|\b(can't|cannot|won't) lose\b"
    r"|\blose (any )?(money|principal)\b|\bsafe\b",
    re.I,
)
GUARANTEE_DENIED_EN = re.compile(
    r"\b(not|no|never|doesn't|don't|isn't|aren't|can't|cannot|won't)\b[^.;!?\n]{0,25}"
    r"\bguarantee|\bnot principal[- ]protected|\b(can|could|may|might) (lose|fall|decline)\b"
    r"|\brisk of (loss|losing)",
    re.I,
)
NO_GUARANTEE_NOTE = register(
    "银行理财产品不保本、不承诺收益，包括低风险的现金管理类产品，均存在本金亏损的可能。",
    "Bank wealth products do not guarantee principal or returns. Even low-risk cash management "
    "products can lose money.",
)


def needs_no_guarantee_note(question: str, reply: str) -> bool:
    asked = _any(GUARANTEE_QUESTION, GUARANTEE_QUESTION_EN, question)
    return asked and not _any(GUARANTEE_DENIED, GUARANTEE_DENIED_EN, reply)


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
        split = SENTENCE_SPLIT_ANY if is_en() else SENTENCE_SPLIT
        parts = re.split(f"({split.pattern})", para)
        out.append(
            "".join(
                s + d
                for s, d in zip(parts[::2], [*parts[1::2], ""], strict=True)
                if not _sentence_steers(s) and not (drop_reassessment and _reassessment(s))
            )
        )
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def _clause_before(text: str, start: int, window: int) -> str:
    before = text[max(0, start - window) : start]
    breaks = list(CLAUSE_BREAK.finditer(before))
    return before[breaks[-1].end() :] if breaks else before


def _negated(text: str, start: int) -> bool:
    clause = NOT_NEGATION.sub("", _clause_before(text, start, NEGATION_WINDOW))
    if any(n in clause for n in NEGATIONS):
        return True
    if not is_en():
        return False
    clause = NOT_NEGATION_EN.sub("", _clause_before(text, start, NEGATION_WINDOW_EN))
    return bool(NEGATIONS_EN.search(clause))


# 引号内的表述若出现在提醒、警示语境中（如：销售说「保本」属于违规宣传），是引述而非承诺
QUOTED = re.compile(r"[「『“\"‘'][^」』”\"’']{1,20}[」』”\"’']")
WARNING_CONTEXT = re.compile(
    r"违规|不应|不要|不能|不得|禁止|警惕|谨慎|虚假|误导|所谓|别信|不可信|不实"
)
WARNING_CONTEXT_EN = re.compile(
    r"misleading|violat|prohibited|not allowed|(don't|do not|never) (believe|trust)|be wary|beware"
    r"|red flag|false|so-called|claims? (like|such as)|warning|caution|shouldn't|should not",
    re.I,
)
QUOTED_EN = re.compile(r"[“\"‘'][^”\"’']{1,40}[”\"’']")


def _quoted_warning(text: str, start: int, end: int) -> bool:
    quotes = list(QUOTED.finditer(text)) + (list(QUOTED_EN.finditer(text)) if is_en() else [])
    stops = "。！？；\n" + (".!?" if is_en() else "")
    for q in quotes:
        if q.start() <= start and end <= q.end():
            left = max(text.rfind(c, 0, start) for c in stops)
            right = min([i for c in stops if (i := text.find(c, end)) != -1] or [len(text)])
            return _any(WARNING_CONTEXT, WARNING_CONTEXT_EN, text[left + 1 : right])
    return False


def _warning_sentence(text: str, start: int) -> bool:
    if not is_en():
        return False
    sentence = next((s for s in _spans(text) if s[0] <= start < s[1]), (0, len(text)))
    return bool(WARNING_SENTENCE_EN.search(text[sentence[0] : sentence[1]]))


def _spans(text: str) -> list[tuple[int, int]]:
    bounds = [0] + [m.end() for m in SENTENCE_SPLIT_ANY.finditer(text)] + [len(text)]
    return list(zip(bounds, bounds[1:], strict=False))


def _negated_after(text: str, end: int) -> bool:
    if not is_en():
        return False
    after = text[end : end + POST_NEGATION_WINDOW_EN]
    after = SENTENCE_SPLIT_ANY.split(after, maxsplit=1)[0]
    return bool(POST_NEGATION_EN.search(after))


def _affirmative_hits(text: str, patterns: list[re.Pattern]) -> list[str]:
    return [
        m.group()
        for p in patterns
        for m in p.finditer(text)
        if not _negated(text, m.start())
        and not _negated_after(text, m.end())
        and not _quoted_warning(text, m.start(), m.end())
        and not _warning_sentence(text, m.start())
    ]


def mentioned_products(text: str) -> set[str]:
    """回答中提到的目录产品（按代码或完整名称匹配）。"""
    compact = text.replace(" ", "")
    lowered = _alnum(text)
    return {
        p.code
        for p in load_catalog().products
        if p.code in text or p.name.replace(" ", "") in compact or _alnum(p.name_en) in lowered
    }


def _alnum(text: str) -> str:
    """英文名比较时忽略大小写、空格与标点（模型常写成 1 Year 而不是 1-Year）。"""
    return re.sub(r"[^0-9a-z]", "", text.lower())


def real_institutions(text: str) -> list[str]:
    hits = [name for name in REAL_INSTITUTIONS if name in text]
    if is_en():
        hits += [m.group() for m in REAL_INSTITUTIONS_EN.finditer(text)]
    return hits


CITATION_RE = re.compile(r"\[(K\d{2}|[A-Z]{2}-[A-Z]\d{2}#[^\]\s]+)\]")


def fake_citations(reply: str, retrieved: Collection[str]) -> list[str]:
    return [cid for cid in CITATION_RE.findall(reply) if cid not in retrieved]


def check_output(
    reply: str,
    permission: Permission,
    grounding: str = "",
    retrieved: Collection[str] = (),
    risk_rating: str | None = None,
    facts: str | None = None,
) -> list[str]:
    """返回违规代码列表；空列表表示通过。

    grounding 是本轮之前已出现的内容：测评前只含客户消息；测评后含客户消息、历史回答和工具结果。
    回答中提到的产品必须在其中出现过，防止模型凭空编造或测评前泄露产品信息。
    retrieved 是本轮检索到的资料编号：回答中的 [编号] 必须在其中，否则视为编造出处。
    risk_rating 是客户的有效评级：用于检查是否推荐了超出评级的产品。
    facts 是核对金额的依据（客户资料 + 此前全部消息与工具结果，不分测评状态）；不传时用 grounding。
    """
    violations = []
    if _affirmative_hits(reply, _rules(PROHIBITED_CLAIMS, PROHIBITED_CLAIMS_EN)):
        violations.append("O-PROHIBITED_CLAIM")
    ungrounded = mentioned_products(reply) - mentioned_products(grounding)
    if permission is Permission.ASSESSMENT_REQUIRED:
        if _affirmative_hits(reply, _rules(RECOMMENDATION, RECOMMENDATION_EN)) or ungrounded:
            violations.append("O-PERMISSION_LEAK")
    else:
        if ungrounded:
            violations.append("O-UNGROUNDED_PRODUCT")
        if unsuitable_recommendations(reply, risk_rating):
            violations.append("O-UNSUITABLE_RECOMMENDATION")
    if _affirmative_hits(reply, _rules(PRESSURE_SALES, PRESSURE_SALES_EN)):
        violations.append("O-PRESSURE_SALES")
    if _affirmative_hits(reply, _rules(RETURN_PITCH, RETURN_PITCH_EN)) or soft_return_pitch(reply):
        violations.append("O-RETURN_PITCH")
    if false_action_claims(reply, grounding):
        violations.append("O-FALSE_ACTION_CLAIM")
    if metric_mixing(reply):
        violations.append("O-METRIC_MIXING")
    if _affirmative_hits(reply, _rules(GIFT_FOR_PURCHASE, GIFT_FOR_PURCHASE_EN)):
        violations.append("O-GIFT_FOR_PURCHASE")
    if permission is Permission.ASSESSED and ungrounded_figures(reply, grounding):
        violations.append("O-UNGROUNDED_FIGURE")
    if steers_reassessment(reply):
        violations.append("O-REASSESSMENT_STEERING")
    if _affirmative_hits(reply, _rules(FALSE_HANDOFF, FALSE_HANDOFF_EN)):
        violations.append("O-FALSE_HANDOFF_CLAIM")
    if ungrounded_amounts(reply, grounding if facts is None else facts):
        violations.append("O-UNGROUNDED_AMOUNT")
    if real_institutions(reply):
        violations.append("O-REAL_INSTITUTION")
    if fake_citations(reply, retrieved):
        violations.append("O-FAKE_CITATION")
    return violations


def offending_snippets(
    reply: str,
    risk_rating: str | None = None,
    grounding: str | None = None,
    facts: str | None = None,
) -> list[str]:
    """违规片段（写入审计记录，便于事后定位模型反复触发的表述）。"""
    hits = _affirmative_hits(reply, _rules(PROHIBITED_CLAIMS, PROHIBITED_CLAIMS_EN))
    hits += _affirmative_hits(reply, _rules(PRESSURE_SALES, PRESSURE_SALES_EN))
    hits += _affirmative_hits(reply, _rules(RETURN_PITCH, RETURN_PITCH_EN))
    hits += _affirmative_hits(reply, _rules(FALSE_HANDOFF, FALSE_HANDOFF_EN))
    hits += metric_mixing(reply) + soft_return_pitch(reply)
    hits += false_action_claims(reply, grounding or "")
    hits += _affirmative_hits(reply, _rules(GIFT_FOR_PURCHASE, GIFT_FOR_PURCHASE_EN))
    if grounding is not None:
        hits += [
            f"产品:{c}" for c in sorted(mentioned_products(reply) - mentioned_products(grounding))
        ]
    if grounding is not None:
        hits += ungrounded_figures(reply, grounding)
        hits += ungrounded_amounts(reply, grounding if facts is None else facts)
    # 测评前任何推荐都是违规；测评后只有推荐超评级产品才是
    hits += unsuitable_recommendations(reply, risk_rating) if risk_rating else []
    recommendation = _rules(RECOMMENDATION, RECOMMENDATION_EN)
    hits += _affirmative_hits(reply, recommendation) if not risk_rating else []
    hits += [s.strip()[:60] for s in _sentences(reply) if _sentence_steers(s)]
    hits += [
        s.strip()[:60]
        for p in PARAGRAPH_SPLIT.split(reply)
        if _paragraph_steers(p)
        for s in _sentences(p)
        if _reassessment(s)
    ]
    return list(dict.fromkeys(hits))[:5]


def describe(
    violations: list[str],
    reply: str,
    risk_rating: str | None = None,
    grounding: str | None = None,
    facts: str | None = None,
) -> str:
    """给 LLM 的改写反馈。"""
    hits = _affirmative_hits(reply, _rules(PROHIBITED_CLAIMS, PROHIBITED_CLAIMS_EN))
    hits += _affirmative_hits(reply, _rules(RECOMMENDATION, RECOMMENDATION_EN))
    hits += offending_snippets(reply, risk_rating, grounding, facts)
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
            "回答中的金额没有来源：金额只能来自工具结果、客户资料或客户自己说的数字；"
            "需要计算（如到手金额、合计、差额）时调用计算工具（calculate_fees、calculate_growth），"
            "不要自己算；不确定时不写具体金额。"
            if "O-UNGROUNDED_AMOUNT" in violations
            else ""
        )
        + (
            "没有调用工具就不能说已完成操作："
            "开售提醒必须调用 set_sale_reminder 成功后才能说已预约；"
            "AI 不能代客户买入或锁定额度，买入需客户本人在产品卡片中确认。"
            if "O-FALSE_ACTION_CLAIM" in violations
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
        + ("客户使用英文界面：改写后的回答必须使用英文。" if is_en() else "")
    )
