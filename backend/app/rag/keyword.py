"""Keyword search: jieba tokenization + BM25 (in memory).

The corpus has only one or two hundred chunks, so in-memory search is enough; no Chinese tokenizer
extension for PostgreSQL is needed (D10).
A custom dictionary adds financial terms so "performance benchmark" isn't split into three words
that match unrelated passages.
"""

import logging

import jieba
from rank_bm25 import BM25Okapi

from app.rag.corpus import Chunk

jieba.setLogLevel(logging.WARNING)

FINANCE_TERMS = [
    "业绩比较基准",
    "七日年化",
    "七日年化收益率",
    "每万份收益",
    "万份收益",
    "现金管理类",
    "固定收益类",
    "固收+",
    "混合类",
    "权益类",
    "净值型",
    "最短持有期",
    "定期开放",
    "封闭式",
    "开放式",
    "申购费",
    "赎回费",
    "管理费",
    "托管费",
    "销售服务费",
    "业绩报酬",
    "存款保险",
    "结构性存款",
    "风险测评",
    "风险承受能力",
    "风险等级",
    "合格投资者",
    "刚性兑付",
    "资管新规",
    "冷静期",
    "登记编码",
    "中国理财网",
    "录音录像",
    "起购金额",
    "提前终止",
    "流动性风险",
]
for term in FINANCE_TERMS:
    jieba.add_word(term, freq=100000)

STOPWORDS = set(
    "的 了 吗 呢 吧 啊 是 在 和 与 及 或 有 我 你 您 这 那 个 能 会 要 就 都 也 还 "
    "怎么 什么 哪些 如何 一下 这个 这款 那个 那款 该 一个 多少".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in jieba.lcut_for_search(text.lower()) if t.strip() and t not in STOPWORDS]


class KeywordIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c.search_text) for c in chunks])

    def search(
        self, query: str, allowed: set[str], k: int, drop: frozenset[str] = frozenset()
    ) -> list[tuple[str, float]]:
        """Return (chunk_id, score), ranked only within allowed; zero scores are dropped.

        drop: words that don't score in this search. E.g. when limited to one product's prospectus,
        "product" just refers to that product
        and doesn't distinguish sections; scoring it would push the sections that say "product" most
        often to the top.
        """
        tokens = [t for t in tokenize(query) if t not in drop]
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            (
                (c.chunk_id, float(s))
                for c, s in zip(self.chunks, scores, strict=True)
                if c.chunk_id in allowed and s > 0
            ),
            key=lambda x: -x[1],
        )
        return ranked[:k]
