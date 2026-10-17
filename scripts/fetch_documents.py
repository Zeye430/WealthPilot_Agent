"""按 data/documents/manifest.yaml 从官方来源下载真实公开产品文件，并校验 SHA-256。

PDF 不提交到仓库（版权原因），clone 后运行本脚本即可复现：
    cd backend && uv run python ../scripts/fetch_documents.py

已存在且校验一致的文件会跳过；来源文件若被更新或下架，校验失败会明确提示。
"""

import hashlib
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/documents/manifest.yaml"
TARGET = ROOT / "data/documents/public"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    entries = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    failures = 0
    for entry in entries:
        path = TARGET / entry["file"]
        if path.exists() and sha256(path.read_bytes()) == entry["sha256"]:
            print(f"✓ 已存在  {entry['file']}")
            continue
        try:
            req = urllib.request.Request(entry["source_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
        except Exception as exc:  # 网络错误或来源下架
            print(f"✗ 下载失败 {entry['file']}：{exc}")
            failures += 1
            continue
        if sha256(data) != entry["sha256"]:
            print(f"✗ 校验不符 {entry['file']}：来源文件可能已更新，请人工核对后更新清单")
            failures += 1
            continue
        path.write_bytes(data)
        print(f"↓ 已下载  {entry['file']}")
        time.sleep(1)  # 控制访问频率
    print(f"\n完成：{len(entries) - failures}/{len(entries)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
