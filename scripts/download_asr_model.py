"""下载本地语音识别模型（约 240MB）。实现见 backend/app/speech/download.py（生产容器中也用它）。

用法（在 backend/ 下）：uv run python ../scripts/download_asr_model.py
网络访问 huggingface.co 较慢时，可设置镜像：HF_ENDPOINT=https://hf-mirror.com
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.speech.download import main  # noqa: E402

if __name__ == "__main__":
    main()
