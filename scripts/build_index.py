"""同步检索索引（知识库 + 产品说明书 → pgvector）。只为新增或变更的内容重新计算向量。

用法（在 backend/ 下）：uv run python ../scripts/build_index.py
修改知识库或重新生成说明书后运行；scripts/dev.sh 启动时会自动执行。
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.knowledge.kb import load_knowledge_base  # noqa: E402
from app.products.catalog import load_catalog  # noqa: E402
from app.rag.corpus import build_corpus  # noqa: E402
from app.rag.embeddings import get_embedder  # noqa: E402
from app.rag.store import sync_index  # noqa: E402


def main() -> None:
    chunks = build_corpus(load_knowledge_base(), load_catalog(), date.today())
    with sessionmaker(bind=get_engine())() as session:
        stats = sync_index(session, chunks, get_embedder())
    print(f"索引同步完成：共 {stats['total']} 块，重新计算 {stats['embedded']} 块，删除 {stats['removed']} 块")


if __name__ == "__main__":
    main()
