"""Local Chinese speech recognition: browser recording (16 kHz mono WAV) → SenseVoice → text.

- The model runs on this server (sherpa-onnx); audio is never sent to third parties;
  it is processed in memory and discarded after recognition, never logged or written to disk.
- Inverse text normalization (ITN) is on: spoken numbers come out as digits (e.g. 45万), so
amounts are easier to check.
- After recognition, fictional brand and product names are corrected from the domain term list (see
lexicon.py).
- Model files are downloaded by scripts/download_asr_model.py; without them the endpoint returns 503
and the frontend hides the mic button.
"""

import io
import re
import wave
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.config import get_settings
from app.core.i18n import L, current
from app.speech.lexicon import correct

SAMPLE_RATE = 16000
MODEL_FILES = ("model.int8.onnx", "tokens.txt")
TAG = re.compile(r"<\|[^|]*\|>")  # language / emotion tags SenseVoice may emit


class AudioError(ValueError):
    pass


class Recognizer(Protocol):
    def transcribe(self, samples: np.ndarray) -> str: ...


def model_installed(model_dir: Path | None = None) -> bool:
    model_dir = model_dir or get_settings().asr_model_dir
    return all((model_dir / name).is_file() for name in MODEL_FILES)


def decode_wav(data: bytes, max_seconds: int) -> np.ndarray:
    """Validate and decode 16 kHz, 16-bit, mono WAV; return float32 samples in [-1, 1]."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE:
                raise AudioError(
                    L(
                        "录音格式应为 16 kHz、16 位、单声道 WAV",
                        "Audio must be 16 kHz, 16-bit, mono WAV",
                    )
                )
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioError(L("无法解析录音文件", "Couldn't read the recording")) from exc
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768
    seconds = len(samples) / SAMPLE_RATE
    if seconds < 0.3:
        raise AudioError(
            L(
                "录音太短，请按住按钮说完再松开",
                "Too short. Hold the button until you finish speaking.",
            )
        )
    if seconds > max_seconds:
        raise AudioError(
            L(
                f"录音超过 {max_seconds} 秒，请分段说",
                f"Recording is over {max_seconds} seconds. Please say it in shorter parts.",
            )
        )
    return samples


def clean(text: str) -> str:
    return TAG.sub("", text).strip()


class SenseVoiceRecognizer:
    def __init__(self, model_dir: Path, threads: int, language: str = "zh"):
        import sherpa_onnx  # lazy import: not loaded unless speech is used

        self._language = language
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=threads,
            language=language,
            use_itn=True,
        )

    def transcribe(self, samples: np.ndarray) -> str:
        stream = self._recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self._recognizer.decode_stream(stream)
        text = clean(stream.result.text)
        # The domain term list corrects homophones of Chinese brand and product names, so it applies
        # only to Chinese recognition
        return correct(text) if self._language == "zh" else text


def get_recognizer() -> Recognizer:
    """Recognizer for the current UI language. The English one loads on first English use (the
    same model takes memory again)."""
    return _recognizer_for(current())


@lru_cache
def _recognizer_for(language: str) -> Recognizer:
    settings = get_settings()
    return SenseVoiceRecognizer(settings.asr_model_dir, settings.asr_threads, language)
