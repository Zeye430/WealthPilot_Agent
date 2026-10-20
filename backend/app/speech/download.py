"""下载本地语音识别模型（SenseVoice int8，约 240MB）到 settings.asr_model_dir。

开发：uv run python ../scripts/download_asr_model.py（在 backend/ 下）
生产容器：uv run --no-dev python -m app.speech.download（deploy/deploy.sh 自动执行）
网络访问 huggingface.co 较慢时，可设置镜像：HF_ENDPOINT=https://hf-mirror.com
模型来源：k2-fsa/sherpa-onnx 转换的 FunAudioLLM/SenseVoiceSmall（开源）。
"""

import os
import urllib.request
from pathlib import Path

from app.core.config import get_settings
from app.speech.recognizer import MODEL_FILES, model_installed

REPO = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"


def download(url: str, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as resp, partial.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done, shown = 0, -10
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            percent = done * 100 // total if total else 0
            if percent >= shown + 10:  # 每 10% 打印一次
                print(f"  {target.name}：{percent}%", flush=True)
                shown = percent
    partial.rename(target)  # 下载完整后才替换，避免中断留下损坏的模型


def main() -> None:
    model_dir = get_settings().asr_model_dir
    if model_installed(model_dir):
        print(f"语音识别模型已安装：{model_dir}")
        return
    model_dir.mkdir(parents=True, exist_ok=True)
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    for name in MODEL_FILES:
        target = model_dir / name
        if not target.is_file():
            download(f"{endpoint}/{REPO}/resolve/main/{name}", target)
    print(f"语音识别模型已下载到 {model_dir}")


if __name__ == "__main__":
    main()
