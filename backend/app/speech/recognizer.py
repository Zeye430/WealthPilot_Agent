"""本地中文语音识别：浏览器录音（16 kHz 单声道 WAV）→ SenseVoice → 文字。

- 模型在本机运行（sherpa-onnx），录音不发送给第三方；
  音频只在内存中处理，识别完即丢弃，不写日志、不落盘。
- 开启逆文本标准化（ITN）：「四十五万」输出为「45万」，金额更容易核对。
- 识别后按领域词表纠正虚构品牌与产品名（见 lexicon.py）。
- 模型文件由 scripts/download_asr_model.py 下载；未安装时接口返回 503，前端隐藏麦克风按钮。
"""

import io
import re
import wave
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.config import get_settings
from app.speech.lexicon import correct

SAMPLE_RATE = 16000
MODEL_FILES = ("model.int8.onnx", "tokens.txt")
TAG = re.compile(r"<\|[^|]*\|>")  # SenseVoice 可能输出的语种 / 情感标签


class AudioError(ValueError):
    pass


class Recognizer(Protocol):
    def transcribe(self, samples: np.ndarray) -> str: ...


def model_installed(model_dir: Path | None = None) -> bool:
    model_dir = model_dir or get_settings().asr_model_dir
    return all((model_dir / name).is_file() for name in MODEL_FILES)


def decode_wav(data: bytes, max_seconds: int) -> np.ndarray:
    """校验并解码 16 kHz、16 位、单声道 WAV，返回 [-1, 1] 的 float32 采样。"""
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE:
                raise AudioError("录音格式应为 16 kHz、16 位、单声道 WAV")
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioError("无法解析录音文件") from exc
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768
    seconds = len(samples) / SAMPLE_RATE
    if seconds < 0.3:
        raise AudioError("录音太短，请按住按钮说完再松开")
    if seconds > max_seconds:
        raise AudioError(f"录音超过 {max_seconds} 秒，请分段说")
    return samples


def clean(text: str) -> str:
    return TAG.sub("", text).strip()


class SenseVoiceRecognizer:
    def __init__(self, model_dir: Path, threads: int):
        import sherpa_onnx  # 延迟导入：未使用语音时不加载

        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=threads,
            language="zh",
            use_itn=True,
        )

    def transcribe(self, samples: np.ndarray) -> str:
        stream = self._recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self._recognizer.decode_stream(stream)
        return correct(clean(stream.result.text))


@lru_cache
def get_recognizer() -> Recognizer:
    settings = get_settings()
    return SenseVoiceRecognizer(settings.asr_model_dir, settings.asr_threads)
