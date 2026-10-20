"""Download the local speech recognition model (about 240 MB). Implemented in
backend/app/speech/download.py (also used in production containers).

Usage (from backend/): uv run python ../scripts/download_asr_model.py
If huggingface.co is slow, use a mirror: HF_ENDPOINT=https://hf-mirror.com
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.speech.download import main  # noqa: E402

if __name__ == "__main__":
    main()
