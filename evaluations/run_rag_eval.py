"""RAG 检索评估：命中率与「资料中未找到」判定（不调用 LLM，结果确定、零成本）。

用法（在 backend/ 下）：
    uv run python ../evaluations/run_rag_eval.py               # 评估线上检索器（混合 + 配额 + 置信度）
    uv run python ../evaluations/run_rag_eval.py --diagnose    # 输出置信度相关分数，用于校准阈值
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yaml  # noqa: E402

from app.knowledge.kb import load_knowledge_base  # noqa: E402
from app.products.catalog import load_catalog  # noqa: E402
from app.rag.corpus import ChunkKind, build_corpus  # noqa: E402
from app.rag.embeddings import get_embedder  # noqa: E402
from app.rag.retriever import InMemoryVectorStore, Retriever  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()

    cases = yaml.safe_load((ROOT / "evaluations/rag_cases.yaml").read_text(encoding="utf-8"))
    chunks = build_corpus(load_knowledge_base(), load_catalog(), date.today())
    embedder = get_embedder()
    retriever = Retriever(chunks, embedder, InMemoryVectorStore(chunks, embedder))
    knowledge = {c.chunk_id for c in chunks if c.kind is ChunkKind.KNOWLEDGE}

    positives = [c for c in cases if c["expected"]]
    negatives = [c for c in cases if not c["expected"]]
    hit1 = hit3 = conf_ok = 0
    for case in positives:
        result = retriever.search(case["query"], case.get("product"))
        ids = [h.chunk.chunk_id for h in result.hits]
        rank = next((i + 1 for i, cid in enumerate(ids) if cid in case["expected"]), None)
        hit1 += rank == 1
        hit3 += rank is not None and rank <= 3
        conf_ok += result.confident
        if rank != 1 or not result.confident:
            print(f"  ⚠ {case['query']} 期望 {case['expected']} 结果 {ids} 置信 {result.confident}")
    rejected = 0
    for case in negatives:
        result = retriever.search(case["query"])
        rejected += not result.confident
        if result.confident:
            print(f"  ⚠ 负例被判为有依据：{case['query']} → {[h.chunk.chunk_id for h in result.hits]}")

    n = len(positives)
    print(f"\n正例 {n} 条：Hit@1 {hit1 / n:.0%}，Hit@3 {hit3 / n:.0%}，判为有依据 {conf_ok / n:.0%}")
    print(f"负例 {len(negatives)} 条：正确判为「资料中未找到」{rejected}/{len(negatives)}")

    if args.diagnose:
        print("\n诊断：知识库范围内的最高向量相似度 / 最高 BM25 分数")
        for case in cases:
            if case.get("product"):
                continue
            vec = embedder.embed_query(case["query"])
            sim = retriever.store.search(vec, knowledge, 1)[0][1]
            kw = retriever.keyword.search(case["query"], knowledge, 1)
            tag = "正" if case["expected"] else "负"
            print(f"  [{tag}] {sim:.3f}  {kw[0][1] if kw else 0:6.2f}  {case['query']}")


if __name__ == "__main__":
    main()
