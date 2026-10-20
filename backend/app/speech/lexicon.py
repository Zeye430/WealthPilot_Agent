"""Domain-term correction for recognized text: fictional brand and product names aren't in the
model's vocabulary and are often heard as homophones.

Approach: build a term list from the product catalog and tier data; if the pinyin (ignoring tones)
of a span in the text equals or is very close to a term,
replace it with the term. Only distinctive terms of 3+ characters are included, so common words
aren't "corrected" into product names.
The list comes from the data files (single source of truth), so new products work automatically.
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
        # long product name → its 4-character brand prefix
        terms.add(head if len(head) <= 5 else head[:4])
        if len(head) == 5:
            terms.add(head[2:])  # drop the 2-character brand prefix
    for tier in load_benefits().tiers:
        terms.add(tier.card_name)
        if tier.card_name.startswith("知岸") and len(tier.card_name) >= 5:
            terms.add(tier.card_name[2:])  # card name without the brand prefix
    return tuple(sorted((t for t in terms if len(t) >= MIN_TERM_LEN), key=len, reverse=True))


def _pinyin(text: str) -> list[str]:
    # lazy import: load the pinyin dictionary only for speech recognition
    from pypinyin import lazy_pinyin

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
    if w[0] != t[0]:  # the first character's sound must match, to reduce false corrections
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
