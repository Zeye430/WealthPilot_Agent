"""Parsing and validating the financial knowledge base.

The knowledge base is kept in Markdown (easy to review by hand); this module splits entries on `###
Kxx` and parses metadata, phrasings, answers and sources.
Only entries marked reviewed and within their review date can be retrieved (expired ones drop out
automatically).
"""

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

KB_PATH = Path(__file__).resolve().parents[3] / "data/knowledge/knowledge_base.md"

STATUSES = ("草稿", "已审核", "待复核", "已下线")
SOURCE_TYPES = ("法规原文", "本系统说明")
ENTRY_RE = re.compile(r"^### (K\d{2}) (.+)$", re.M)
SOURCE_ROW_RE = re.compile(r"^\| (S\d{2}) \| (.+?) \| (.*?) \| (.*?) \| (.+?) \|$", re.M)
QUOTE_RE = re.compile(r"「([^」]{4,})」")
URL_RE = re.compile(r"\((https?://[^)\s]+)\)")


class KnowledgeError(ValueError):
    pass


class Source(BaseModel):
    id: str
    title: str
    doc_number: str
    date: str
    url: str | None  # explanatory sources from this system have no link


class Citation(BaseModel):
    """One source in an entry: the cited source ID, clause and excerpt of the original text."""

    source_ids: list[str]
    text: str
    quotes: list[str]


class Entry(BaseModel):
    id: str
    question: str
    status: str
    version: int
    verified_at: date
    review_due: date
    reviewer: str
    aliases: list[str]
    source_type: str
    answer: str
    citations: list[Citation]

    def is_retrievable(self, today: date) -> bool:
        return self.status == "已审核" and self.review_due >= today

    @property
    def search_text(self) -> str:
        """Text used for retrieval: title + common phrasings + answer. Phrasings let casual
        questions match too."""
        return f"{self.question}\n常见问法：{'；'.join(self.aliases)}\n{self.answer}"


class KnowledgeBase(BaseModel):
    sources: dict[str, Source]
    entries: list[Entry]

    def retrievable(self, today: date) -> list[Entry]:
        return [e for e in self.entries if e.is_retrievable(today)]

    def get(self, entry_id: str) -> Entry | None:
        return next((e for e in self.entries if e.id == entry_id), None)


def _parse_meta(line: str, entry_id: str) -> dict:
    if not line.startswith("- 元数据："):
        raise KnowledgeError(f"{entry_id}：标题下第一行应为「- 元数据：」")
    fields = dict(part.split("=", 1) for part in line.removeprefix("- 元数据：").split("；"))
    try:
        meta = {
            "status": fields["状态"],
            "version": int(fields["版本"]),
            "verified_at": date.fromisoformat(fields["核对日期"]),
            "review_due": date.fromisoformat(fields["复核到期"]),
            "reviewer": fields["审核人"],
        }
    except (KeyError, ValueError) as exc:
        raise KnowledgeError(f"{entry_id}：元数据格式错误（{exc}）") from exc
    if meta["status"] not in STATUSES:
        raise KnowledgeError(f"{entry_id}：未知状态「{meta['status']}」")
    return meta


def _parse_sources(text: str) -> dict[str, Source]:
    sources = {}
    for sid, title, number, when, link in SOURCE_ROW_RE.findall(text):
        url = URL_RE.search(link)
        sources[sid] = Source(
            id=sid,
            title=title.strip(),
            doc_number=number.strip(),
            date=when.strip(),
            url=url.group(1) if url else None,
        )
    return sources


def parse(text: str) -> KnowledgeBase:
    sources = _parse_sources(text)
    matches = list(ENTRY_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        entry_id, question = m.group(1), m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.end() : end].split("\n---")[0].split("\n## ")[0]
        lines = [ln for ln in block.strip().splitlines()]
        meta = _parse_meta(lines[0], entry_id)

        aliases, source_type, answer_lines, citations = [], None, [], []
        section = "header"
        for line in lines[1:]:
            if line.startswith("- 常见问法："):
                aliases = [
                    a.strip() for a in line.removeprefix("- 常见问法：").split("；") if a.strip()
                ]
            elif line.startswith("- 来源类型："):
                source_type = line.removeprefix("- 来源类型：").strip()
                section = "answer"
            elif line.startswith("出处："):
                section = "citations"
            elif section == "answer" and line.strip():
                answer_lines.append(line.strip())
            elif section == "citations" and line.startswith("- "):
                body = line.removeprefix("- ")
                citations.append(
                    Citation(
                        source_ids=re.findall(r"S\d{2}", body.split("：")[0]),
                        text=body,
                        quotes=QUOTE_RE.findall(body),
                    )
                )

        if not source_type or not any(source_type.startswith(t) for t in SOURCE_TYPES):
            raise KnowledgeError(f"{entry_id}：来源类型缺失或未知")
        if not answer_lines:
            raise KnowledgeError(f"{entry_id}：缺少回答")
        if not citations:
            raise KnowledgeError(f"{entry_id}：至少需要一条出处")
        for c in citations:
            for sid in c.source_ids:
                if sid not in sources:
                    raise KnowledgeError(f"{entry_id}：引用了不存在的出处 {sid}")
        entries.append(
            Entry(
                id=entry_id,
                question=question,
                aliases=aliases,
                source_type=source_type,
                answer="\n".join(answer_lines),
                citations=citations,
                **meta,
            )
        )

    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise KnowledgeError("条目编号重复")
    return KnowledgeBase(sources=sources, entries=entries)


@lru_cache
def load_knowledge_base(path: Path = KB_PATH) -> KnowledgeBase:
    return parse(path.read_text(encoding="utf-8"))
