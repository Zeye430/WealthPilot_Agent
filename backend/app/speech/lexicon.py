"""识别结果的领域词纠错：虚构品牌和产品名（如「知岸稳享」）不在识别模型的词汇里，常被识别成同音词。

做法：从产品目录和等级数据生成词表，若识别文字中某一片段的拼音（不计声调）与词表词相同或非常接近，
则替换为词表词。只收录 3 个字以上、较有区分度的词，避免把「定向」之类的常用词改成「定享」。
词表来自数据文件（单一数据源），新增产品后自动生效。
"""

import re
from functools import lru_cache

from app.benefits.service import load_benefits
from app.products.catalog import load_catalog

CJK_RUN = re.compile(r"[一-鿿]+")
MIN_TERM_LEN = 3


@lru_cache
def domain_terms() -> tuple[str, ...]:
    terms: set[str] = set()
    for product in load_catalog().products:
        run = CJK_RUN.match(product.name)
        if not run:
            continue
        head = run.group()
        terms.add(head if len(head) <= 5 else head[:4])  # 「知岸稳享每日开放」→「知岸稳享」
        if len(head) == 5:
            terms.add(head[2:])  # 「知岸活钱宝」→「活钱宝」
    for tier in load_benefits().tiers:
        terms.add(tier.card_name)
        if tier.card_name.startswith("知岸") and len(tier.card_name) >= 5:
            terms.add(tier.card_name[2:])  # 「知岸臻享卡」→「臻享卡」
    return tuple(sorted((t for t in terms if len(t) >= MIN_TERM_LEN), key=len, reverse=True))


def _pinyin(text: str) -> list[str]:
    from pypinyin import lazy_pinyin  # 延迟导入：只在语音识别时加载拼音词典

    return lazy_pinyin(text)


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _close(window: str, term: str) -> bool:
    w, t = _pinyin(window), _pinyin(term)
    if w[0] != t[0]:  # 首字读音必须一致，降低误改
        return False
    allowed = 1 if len(term) <= 4 else 2
    return _distance("".join(w), "".join(t)) <= allowed


def correct(text: str, terms: tuple[str, ...] | None = None) -> str:
    for term in terms if terms is not None else domain_terms():
        n, i = len(term), 0
        while i <= len(text) - n:
            window = text[i : i + n]
            if window != term and CJK_RUN.fullmatch(window) and _close(window, term):
                text = text[:i] + term + text[i + n :]
                i += n
            else:
                i += 1
    return text
