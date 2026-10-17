"""关键词检索：jieba 分词 + BM25（内存）。

语料只有一两百块，内存检索足够；不必给 PostgreSQL 安装中文分词扩展（D10）。
自定义词典补充金融术语，避免「业绩比较基准」被切成「业绩 / 比较 / 基准」后与无关段落误配。
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
        """返回 (chunk_id, 分数)，只在 allowed 范围内排序；分数为 0 的不返回。

        drop：本次检索中不计分的词。例如已限定在某款产品的说明书内时，「产品」只是指代该产品，
        没有区分章节的作用，反而会让「产品」出现最多的章节排到前面。
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
