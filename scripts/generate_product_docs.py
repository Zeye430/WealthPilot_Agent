"""Generate fictional product prospectuses from data/products/products.yaml into
data/products/docs/.

Run after changing product terms (from backend/): uv run python ../scripts/generate_product_docs.py
The test test_generated_docs_are_up_to_date checks that prospectuses match the terms.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.products.catalog import load_catalog  # noqa: E402
from app.products.documents import render  # noqa: E402

DOCS_DIR = ROOT / "data/products/docs"


def main() -> None:
    catalog = load_catalog()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    expected = set()
    for product in catalog.products:
        path = DOCS_DIR / f"{product.code}.md"
        path.write_text(render(product, catalog), encoding="utf-8")
        expected.add(path.name)
    for stale in set(p.name for p in DOCS_DIR.glob("*.md")) - expected:
        (DOCS_DIR / stale).unlink()
        print(f"删除过期说明书 {stale}")
    print(f"已生成 {len(expected)} 份说明书 → {DOCS_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
