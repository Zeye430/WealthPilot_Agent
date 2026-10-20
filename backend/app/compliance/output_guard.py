"""Output review: deterministic checks before a reply is sent. No LLM calls.

Rules target **affirmative statements**: "wealth products are not principal-protected" is a
legitimate fact; "guaranteed returns" is a prohibited promise.

English UI (P8-2b): every rule has an English version (*_EN). The Chinese UI uses only the Chinese
rules (behavior unchanged);
the English UI applies both sets, so Chinese phrasing slipped into an English reply is still caught.
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

# A negation word earlier in the same clause as the hit makes it a negated statement, not a
# violation.
# Chinese negations often sit far from the word they negate ("no wealth product at all is principal-
# and return-guaranteed"),
# so the whole clause is checked, up to 20 characters.
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
# contain 不 but are not negations
NOT_NEGATION = re.compile(r"不仅|不但|不只|不光|毫不|无不|不可思议")
CLAUSE_BREAK = re.compile(r"[，,。！？；;：:\n]")
NEGATION_WINDOW = 20
# English negations usually sit more characters away from the negated word ("we can't promise you
# any guaranteed returns")
# Reported speech ("any product claiming...", "if anyone tells you...") is treated like negation: it
# isn't the AI's own promise
NEGATIONS_EN = re.compile(
    r"\b(not|no|never|cannot|without|neither|nor|nothing|none|nobody|avoid|instead of|"
    r"claim(s|ing|ed)?|anyone|someone|beware|wary|so-called|marketed as|advertis\w*|"
    r"watch out|be careful|red flag)\b|n't\b",
    re.I,
)
NOT_NEGATION_EN = re.compile(r"\bnot only\b|\bno doubt\b|\bno matter\b", re.I)
# Found in scenario evaluation: "regulations do not allow me to sell you a product with a guaranteed
# return"
# has 60+ characters between the negation and the keyword, so the English window is 100 characters
# (about 15-20 words), still bounded by the clause
NEGATION_WINDOW_EN = 100
# English often puts the negation after the subject (scenario S02): "Principal-protected bank
# products no longer exist"
# "principal-protected products with guaranteed returns are no longer issued"
POST_NEGATION_EN = re.compile(
    r"\b(no longer|don't exist|do not exist|doesn't exist|does not exist|"
    r"(are|is)n't (available|offered|allowed|permitted|issued|sold)|"
    r"(are|is) not (available|offered|allowed|permitted|issued|sold)|"
    r"(have|has) been (phased out|abolished|banned|eliminated)|(are|is) (prohibited|banned))\b",
    re.I,
)
POST_NEGATION_WINDOW_EN = 80
# The same sentence is clearly a warning (with or without quotes): the reported claim is called
# non-compliant or misleading
WARNING_SENTENCE_EN = re.compile(
    r"misleading|non-?compliant|not compl(y|iant)|violat\w*|illegal|prohibited|"
    r"not (being )?truthful|red flag|scam|fraud\w*|false claim",
    re.I,
)
# English sentence split: end punctuation must be followed by whitespace, so a decimal point (2.5%)
# isn't a sentence end
SENTENCE_SPLIT_EN = r"(?<=[.!?;])\s+"


def _rules(zh: list[re.Pattern], en: list[re.Pattern]) -> list[re.Pattern]:
    """Rules active in the current language: Chinese UI uses Chinese rules; English UI uses both."""
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
        # Only block assertions such as "there's / it carries no risk";
        # "capital preservation with no risk" describes the customer's goal and is allowed
        r"\b(there'?s|there is|it'?s|carries|carry|has|have|involves?)\s+"
        r"(virtually\s+|basically\s+|almost\s+|absolutely\s+)?no risk\b(?!-)",
        r"\b(can't|cannot|won't|will not|never) lose\b",
        r"\b(sure|surefire|safe) (bet|thing|win)\b",
        r"\b(definitely|certainly|surely|absolutely)\s+(will\s+|can\s+)?"
        r"(earn|make money|reach|achieve|double|profit|beat)",
    )
]

# Recommendation language that must not appear before a risk assessment
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
        # Same as the Chinese rule ("the products that suit you are / there are"): an asserting verb
        # is required.
        # "After the assessment I can pick suitable products for you" invites an assessment and
        # isn't a recommendation (eval R03)
        r"\b(suitable|right|best) (product|option|choice)s? for you\s+(is|are|would be|include)\b",
    )
]


# Real wealth-management company names: by product-owner decision, no real institution's product
# information appears (fictional institutions only)
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
# English names of real wealth-management companies (including common abbreviations)
REAL_INSTITUTIONS_EN = re.compile(
    r"\b(ICBC|CCB|ABC|BOC|BoCom|Bank of Communications|PSBC|Postal Savings|CMB|China Merchants|"
    r"CIB|Industrial Bank|CITIC|Everbright|Ping ?An|Hua ?Xia|SPDB|Minsheng|CGB|China Guangfa|"
    r"Bohai|Hengfeng|Ningbo|Hangzhou|Huishang|Nanjing|Qingdao|Jiangsu|Bank of Shanghai|"
    r"Bank of Beijing|Chongqing Rural)\s+(Bank\s+)?Wealth\b"
    r"|\b(BlackRock CCB|Schroders? BoCom|Goldman Sachs ICBC|Amundi BOC)\b",
    re.I,
)


# Steering toward a higher risk rating: suggesting a re-assessment to reach a return target is a
# classic suitability violation (the assessment must reflect the customer's real situation)
REASSESSMENT = re.compile(
    r"重新(完成|进行|做)?(一次)?(风险)?(承受能力)?(测评|评估)"
    r"|调(整|高).{0,4}(评级|风险等级)|提高.{0,4}风险承受"
)
# Steering if it appears in the same sentence as a re-assessment: returns, higher risk, or the
# assessment as a way to "unlock" higher-risk products
RISK_OR_RETURN = re.compile(
    r"收益|更高(的)?风险|高风险|PR[3-5]|波动|权益类|相应等级|更高(的)?(风险)?等级"
)
# Another form: suggesting (via the relationship manager) to evaluate whether a higher risk level is
# needed
RISK_UPGRADE = re.compile(r"(更高|提高|调高|提升)(的)?.{0,2}(风险等级|评级|风险承受)")
SUGGESTION = re.compile(r"建议|可以|可|考虑|评估|是否需要|如需|若需")
# A sentence that states the limitation (doesn't match / exceeds the rating) explains a trade-off
# rather than suggesting a higher rating
LIMITATION = re.compile(r"不匹配|超出|不符合|无法购买|不能购买|无权")
SENTENCE_SPLIT = re.compile(r"[。！？；\n]")
# English: retake / redo the profile, reassess;
# "complete your risk profile" is a normal prompt for an unprofiled customer and is allowed
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


# Needs-based recommendations (product-owner decision, 2026-10-18): recommending within the rating
# is allowed; these remain prohibited
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
# 1. Recommending products above the customer's rating
# 2. Sales pressure that creates urgency
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
# 4. Tying gifts, points or cash back to buying a specific product (benefits depend only on total
# assets; see data/benefits/benefits.yaml)
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
# 3. Using returns as the reason for a recommendation
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


# Claiming a human has joined: the AI only replies while no relationship manager has taken over, so
# any "joined" claim is false
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


# Claiming an action that didn't happen (found in scenario N02: the model said "sale reminder set"
# without calling the tool).
# Reminders: only allowed when this turn's tool results or the customer's reminder records contain
# "sale reminder set";
# Purchases: the AI can't buy on the customer's behalf, so any "bought for you" claim is false.
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


# Soft return comparisons (P8-2b scenario P05, in both languages): no "performance benchmark"
# wording,
# but higher returns used as the reason in a recommendation or allocation, e.g. "put the rest in
# Steady Daily Open for a bit more return"
# or "This is the highest-yielding option". Sentences explaining the risk trade-off (higher return
# means higher risk) are allowed.
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


# Comparing returns across measures: a performance benchmark and a 7-day annualized yield (cash
# management) aren't comparable.
# Comparison tables keep measures in separate columns; this rule blocks comparisons in the reply
# text (found in P7 scenario P05; prompt constraints proved unreliable)
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
    """A comparison in one sentence, or a paragraph that mentions cash management first and then
    says a product has a "higher benchmark" (scenario P05)."""
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


# Return figures need a source: percentages next to a performance benchmark or 7-day yield must
# appear in this turn's tool results or earlier messages.
# P7 scenario N02 found the model quoting a new product's benchmark of 2.80%-3.30% as 2.60%-3.20%.
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# Only figures right after the metric name (including ranges) are checked, not other percentages in
# the sentence such as allocation shares (scenario V02)
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


# Amounts need a source (P8-4): RMB amounts in a reply must appear in tool results, the customer
# profile or the customer's own words.
# "All money math is done in code" is a hard rule; P8-2b scenarios found the model occasionally
# computing net proceeds itself, and wrongly
# (¥100,000 with a ¥500 redemption fee written as ¥95,500 received).
# A 0.1% rounding difference is allowed (¥1.6289M vs 1,628,894.63, a 0.0003% difference).
# 0.5% was used before: in the English eval the model wrote 99,500 as 995,000, exactly 0.5% from
# 1,000,000, and it slipped through.
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
    """Amounts in the knowledge base (checked against the source, e.g. the ¥500,000
    deposit-insurance cap): quoting them isn't fabrication."""
    text = KB_PATH.read_text(encoding="utf-8")
    return frozenset(v for _, v in _amounts(text))


# Illustrative amounts (product-owner decision, 2026-10-19): general explanations may use example
# amounts,
# but the same sentence must say it's an assumption, and only round figures are allowed (e.g.
# ¥600,000, ¥100,000).
# Calculated results (e.g. ¥103,000 or 1,790,847.70) aren't round figures and must still come from a
# tool: the model can't compute them.
ASSUMPTION = re.compile(r"假设|假如|假定|举例|举个例子|例如|比如|打个比方|以[^。！？；\n]{0,8}为例")
ASSUMPTION_EN = re.compile(
    r"\b(suppose|supposing|assume|assuming|assumption|hypothetical(ly)?|for example|"
    r"for instance|e\.g\.|let's say|say you|imagine)\b",
    re.I,
)
ILLUSTRATIVE_MAX_SIGNIFICANT_DIGITS = 2


def _illustrative(value: Decimal) -> bool:
    """An integer with at most 2 significant digits (600,000, 450,000, 1,500,000): looks like an
    example, not a calculation."""
    if value != value.to_integral_value():
        return False
    digits = str(int(abs(value))).rstrip("0")
    return len(digits) <= ILLUSTRATIVE_MAX_SIGNIFICANT_DIGITS


def _assumption_sentences(reply: str) -> list[str]:
    # The period in "e.g." doesn't end a sentence; replace it first so the marker and the amount
    # stay in one sentence
    text = re.sub(r"\be\.g\.", "eg,", reply, flags=re.I)
    pattern = re.compile(ASSUMPTION_EN.pattern.replace(r"e\.g\.", r"eg"), re.I)
    return [s for s in SENTENCE_SPLIT_ANY.split(text) if ASSUMPTION.search(s) or pattern.search(s)]


def ungrounded_amounts(reply: str, facts: str) -> list[str]:
    known = {v for _, v in _amounts(facts)} | _reference_amounts()
    known |= {v for n in BARE_NUMBER.findall(facts) if (v := _to_decimal(n)) is not None}
    assumed = {v for s in _assumption_sentences(reply) for _, v in _amounts(s) if _illustrative(v)}
    hits = []
    for text, value in _amounts(reply):
        if value == 0 or value in assumed:
            continue
        if not any(abs(value - k) <= max(abs(k) * AMOUNT_TOLERANCE, Decimal(1)) for k in known):
            hits.append(text)
    return list(dict.fromkeys(hits))


def unsuitable_recommendations(text: str, risk_rating: str | None) -> list[str]:
    """Sentences recommending a product above the customer's rating (allowed if the sentence
    states the limitation, e.g. "exceeds / not recommended")."""
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
    # A paragraph saying "5% needs PR3 or higher" followed by "you can retake the assessment if
    # things change" reads as steering
    # (found in P7 scenario M01). When discussing returns or higher risk, don't bring up a
    # re-assessment.
    return bool(_reassessment(p) and _any(RISK_OR_RETURN, RISK_OR_RETURN_EN, p))


def steers_reassessment(text: str) -> bool:
    return any(_sentence_steers(s) for s in _sentences(text)) or any(
        _paragraph_steers(p) for p in PARAGRAPH_SPLIT.split(text)
    )


# When the customer asks outright which product is principal- or return-guaranteed, the reply must
# clearly say none is.
# The model sometimes only says "a benchmark isn't a promise" or "deposits are protected" and
# dodges, which can suggest low-risk wealth products are protected too,
# so code adds the standard statement (found in P7 scenario S02)
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
    """Remove sentences that steer toward a higher rating. They are add-on suggestions; the rest of
    the reply stays complete.

    For paragraph-level steering, only the sentences mentioning a re-assessment are removed; the
    explanation of the risk/return trade-off stays.
    """
    paragraphs = re.split(f"({PARAGRAPH_SPLIT.pattern})", reply)
    out = []
    for i, para in enumerate(paragraphs):
        if i % 2:  # paragraph separator
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


# A quoted phrase in a reminder or warning context (e.g. a salesperson saying "principal-protected"
# is false advertising) is a quotation, not a promise
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
    """Catalog products mentioned in the reply (matched by code or full name)."""
    compact = text.replace(" ", "")
    lowered = _alnum(text)
    return {
        p.code
        for p in load_catalog().products
        if p.code in text or p.name.replace(" ", "") in compact or _alnum(p.name_en) in lowered
    }


def _alnum(text: str) -> str:
    """Compare English names ignoring case, spaces and punctuation (the model often writes 1 Year
    instead of 1-Year)."""
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
    """Return a list of violation codes; an empty list means the reply passes.

    grounding is what appeared before this turn: before an assessment, only customer messages;
    after, customer messages, earlier replies and tool results.
    Products mentioned in the reply must appear there, so the model can't invent products or leak
    them before an assessment.
    retrieved is the set of source IDs found this turn: every [ID] in the reply must be in it,
    otherwise it's a fabricated citation.
    risk_rating is the customer's valid rating, used to check for recommendations above it.
    facts is the basis for checking amounts (customer profile + all earlier messages and tool
    results, regardless of assessment state); defaults to grounding.
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
    """Offending snippets (written to the audit log to find phrasing the model keeps producing)."""
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
    # Before an assessment any recommendation is a violation; after it, only recommending above the
    # rating is
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
    """Rewrite feedback for the LLM."""
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
        + (
            "引用了本轮没有检索到的资料编号：要引用就先调用 search_documents 检索"
            "（上一轮检索过的也要重新检索），否则删去这些编号。"
            if "O-FAKE_CITATION" in violations
            else ""
        )
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
            "回答中的金额没有来源，上面列出的金额不能原样再写。请这样改："
            "（1）收益、终值、费用、到手金额：先调用计算工具（calculate_growth、calculate_fees），"
            "再按工具结果作答；"
            "（2）工具算不了的差额或合计：不写具体数字，改用文字描述，"
            "如「超出 50 万元的部分」「两者之和」；"
            "（3）举例时只写假设的整数金额（同一句写明「假设」或「例如」）和资料中的限额。"
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
