"""Download the local speech recognition model (SenseVoice int8, about 240 MB) to
settings.asr_model_dir.

Development: uv run python ../scripts/download_asr_model.py (from backend/)
Production container: uv run --no-dev python -m app.speech.download (run automatically by
deploy/deploy.sh)
If huggingface.co is slow, use a mirror: HF_ENDPOINT=https://hf-mirror.com
Model source: FunAudioLLM/SenseVoiceSmall (open source), converted by k2-fsa/sherpa-onnx.
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
            if percent >= shown + 10:  # print every 10%
                print(f"  {target.name}：{percent}%", flush=True)
                shown = percent
    # replace only after a complete download, so an interruption can't leave a corrupt model
    partial.rename(target)


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
