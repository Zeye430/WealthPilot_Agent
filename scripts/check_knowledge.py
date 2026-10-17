"""知识库维护检查（docs/KNOWLEDGE_BASE_DESIGN.md §4.4）。

检查四项：格式 / 到期 / 链接可访问 / 摘录原文是否仍在来源页面。
用法（在 backend/ 下）：
    uv run python ../scripts/check_knowledge.py            # 全部检查（需要联网）
    uv run python ../scripts/check_knowledge.py --offline  # 只检查格式与到期
退出码：格式错误为 2；有报警（过期、链接失效、原文缺失）为 1；全部通过为 0。
"""

import argparse
import html
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

from app.knowledge.kb import KnowledgeError, load_knowledge_base  # noqa: E402

DUE_SOON = timedelta(days=30)
UA = {"User-Agent": "Mozilla/5.0 (WealthPilot knowledge check)"}


def normalize(text: str) -> str:
    """去掉空白、HTML 实体与全角/半角标点差异（NFKC），使摘录与网页正文可比较。

    不同转载页面的标点宽度可能不同（如「，」与「,」），这属于排版差异而非内容变化。
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", html.unescape(text)))


def page_text(url: str) -> str:
    resp = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.content
    charset = resp.charset_encoding or (
        m.group(1).decode() if (m := re.search(rb'charset=["\']?([\w-]+)', raw[:2000])) else "utf-8"
    )
    text = raw.decode(charset, errors="ignore")
    return normalize(re.sub(r"<[^>]+>", "", text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    try:
        kb = load_knowledge_base()
    except KnowledgeError as exc:
        print(f"✗ 格式错误：{exc}")
        return 2
    print(f"✓ 格式：{len(kb.entries)} 条，出处 {len(kb.sources)} 个")

    alerts = 0
    today = date.today()
    for e in kb.entries:
        if e.status != "已审核":
            print(f"· {e.id} 状态为「{e.status}」，不会被检索")
        elif e.review_due < today:
            print(f"✗ {e.id} 已过复核到期日 {e.review_due}，已自动停止作为依据，请复核")
            alerts += 1
        elif e.review_due - today <= DUE_SOON:
            print(f"! {e.id} 将于 {e.review_due} 到期，请安排复核")
    if args.offline:
        return 1 if alerts else 0

    # 按来源页面汇总摘录：每个页面只请求一次
    quotes_by_url: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in kb.entries:
        for c in e.citations:
            urls = [kb.sources[s].url for s in c.source_ids if kb.sources[s].url]
            for q in c.quotes:
                for url in urls:
                    quotes_by_url[url].append((e.id, q))

    missing: dict[tuple[str, str], list[str]] = {}
    for url, quotes in quotes_by_url.items():
        try:
            text = page_text(url)
        except Exception as exc:
            print(f"✗ 链接无法访问：{url}（{type(exc).__name__}）")
            alerts += 1
            continue
        found = 0
        for entry_id, quote in quotes:
            # 摘录中的「……」表示省略，分段核对
            parts = [normalize(p) for p in quote.split("……") if len(normalize(p)) >= 4]
            if all(p in text for p in parts):
                found += 1
            else:
                missing.setdefault((entry_id, quote), []).append(url)
        print(f"✓ {url}：{found}/{len(quotes)} 条摘录仍在页面上")

    # 一条摘录可能对应多个来源页面，只要在其中一个页面找到即可
    really_missing = {
        k: urls for k, urls in missing.items()
        if len(urls) == sum(1 for u, qs in quotes_by_url.items() if (k[0], k[1]) in qs)
    }
    for (entry_id, quote), _ in really_missing.items():
        print(f"✗ {entry_id} 的摘录未在来源页面找到：「{quote[:40]}」，建议改为「待复核」")
        alerts += 1

    print("\n全部通过" if not alerts else f"\n共 {alerts} 项报警")
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
