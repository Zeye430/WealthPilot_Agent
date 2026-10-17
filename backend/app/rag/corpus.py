"""检索语料：知识库条目 + 虚构产品说明书章节。

切块原则：
- 说明书按「## 章节」切分：一个章节是一个完整语义单元，引用也能精确到章节。
- 知识库一条一块：检索文本包含标题、常见问法与回答，口语化提问也能命中。
只有「已审核」且未过期的知识库条目会进入语料（过期自动降级）。
"""

import hashlib
import re
from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from app.knowledge.kb import KnowledgeBase
from app.products.catalog import Catalog

DOCS_DIR = Path(__file__).resolve().parents[3] / "data/products/docs"
SECTION_RE = re.compile(r"^## (.+)$", re.M)

# 说明书章节的口语化检索别名：客户说「能投股票吗」，说明书写的是「投资范围与投资比例」。
# 只用于检索（search_text），不进入提供给 LLM 的正文。作用与知识库的「常见问法」相同。
SECTION_ALIASES = {
    "重要须知": "注意事项 风险提示 风险等级为什么 适合什么人",
    "一": "基本信息 风险等级 多少钱起买 起购 成立 到期",
    "二": "投资什么 投向哪里 能投股票吗 投资范围 资产配置",
    "三": "怎么买 怎么赎回 取钱 多久能取出来 到账时间 开放日",
    "四": "费用 手续费 收多少钱 管理费 托管费 赎回费",
    "五": "收益 业绩比较基准 七日年化 净值 过往业绩",
    "六": "提前终止 产品终止",
    "七": "风险 会亏吗 最坏情况 亏损",
    "八": "信息披露 公告 去哪看净值",
}


class ChunkKind(StrEnum):
    KNOWLEDGE = "KNOWLEDGE"
    PRODUCT_DOC = "PRODUCT_DOC"


class Chunk(BaseModel):
    chunk_id: str  # K17 或 ZA-F03#四
    kind: ChunkKind
    title: str  # 展示用标题
    section: str | None
    product_code: str | None
    text: str  # 用于检索与提供给 LLM 的正文
    version: str  # 知识库条目版本 / 产品目录版本
    review_due: date | None
    source_label: str  # 「法规原文」或「本系统说明」/「产品说明书」

    search_aliases: str = ""  # 仅用于检索的口语化别名

    @property
    def search_text(self) -> str:
        return f"{self.text}\n{self.search_aliases}" if self.search_aliases else self.text

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.title}\n{self.search_text}".encode()).hexdigest()[:16]


def knowledge_chunks(kb: KnowledgeBase, today: date) -> list[Chunk]:
    chunks = []
    for e in kb.retrievable(today):
        regulatory = any(not sid.startswith("S9") for c in e.citations for sid in c.source_ids)
        chunks.append(
            Chunk(
                chunk_id=e.id,
                kind=ChunkKind.KNOWLEDGE,
                title=f"知识库 {e.id} {e.question}",
                section=None,
                product_code=None,
                text=e.search_text,
                version=f"v{e.version}",
                review_due=e.review_due,
                source_label="法规原文" if regulatory else "本系统说明",
            )
        )
    return chunks


def product_doc_chunks(catalog: Catalog, docs_dir: Path = DOCS_DIR) -> list[Chunk]:
    chunks = []
    for product in catalog.products:
        text = (docs_dir / f"{product.code}.md").read_text(encoding="utf-8")
        sections = list(SECTION_RE.finditer(text))
        for i, m in enumerate(sections):
            heading = m.group(1).strip()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
            body = text[m.end() : end].strip()
            numeral = heading.split("、")[0] if "、" in heading else heading
            chunks.append(
                Chunk(
                    chunk_id=f"{product.code}#{numeral}",
                    kind=ChunkKind.PRODUCT_DOC,
                    title=f"《{product.name}》说明书",
                    section=heading,
                    product_code=product.code,
                    # 正文前加产品名与章节名：「费用」这类通用章节才能区分属于哪款产品
                    text=f"《{product.name}》（{product.code}）说明书 · {heading}\n{body}",
                    version=catalog.catalog_version,
                    review_due=None,
                    source_label="产品说明书",
                    search_aliases=SECTION_ALIASES.get(numeral, ""),
                )
            )
    return chunks


def build_corpus(kb: KnowledgeBase, catalog: Catalog, today: date) -> list[Chunk]:
    return knowledge_chunks(kb, today) + product_doc_chunks(catalog)
