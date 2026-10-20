"""Speech to text: WAV validation, tag cleanup, domain-term correction, endpoint (fake
recognizer, no model files needed)."""

import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import speech
from app.main import app
from app.speech.lexicon import correct
from app.speech.recognizer import SAMPLE_RATE, AudioError, clean, decode_wav


def wav(seconds: float = 1.0, rate: int = SAMPLE_RATE, channels: int = 1) -> bytes:
    frames = np.zeros(int(seconds * rate) * channels, dtype="<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def test_decode_wav_accepts_16k_mono():
    samples = decode_wav(wav(1.0), max_seconds=60)
    assert samples.dtype == np.float32 and len(samples) == SAMPLE_RATE


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (wav(1.0, rate=44100), "16 kHz"),
        (wav(1.0, channels=2), "单声道"),
        (wav(0.1), "太短"),
        (wav(3.0), "超过 2 秒"),
        (b"not a wav", "无法解析"),
    ],
)
def test_decode_wav_rejects_bad_audio(data, message):
    with pytest.raises(AudioError, match=message):
        decode_wav(data, max_seconds=2)


def test_clean_strips_sensevoice_tags():
    assert clean("<|zh|><|NEUTRAL|><|Speech|><|withitn|>我有45万。") == "我有45万。"


def test_domain_terms_corrected_by_pinyin():
    # Observed: macOS synthesized speech recognized by SenseVoice as homophones of the brand and
    # product names
    assert correct("挚爱文享30天持有和活钱保有什么区别？") == "知岸稳享30天持有和活钱宝有什么区别？"
    assert correct("鸿雨臻享一年封闭怎么样") == "鸿屿臻享一年封闭怎么样"
    assert correct("我能办真想卡吗") == "我能办臻享卡吗"
    # Common words must not be changed into similar product names
    assert correct("定向增发和治安问题") == "定向增发和治安问题"


class FakeRecognizer:
    def transcribe(self, samples):
        return "我有45万，想买一年期的理财"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(speech, "model_installed", lambda: True)
    monkeypatch.setattr(speech, "get_recognizer", lambda: FakeRecognizer())
    return TestClient(app, headers={"X-Demo-User": "pytest_customer"})


def test_transcribe_returns_text(client):
    resp = client.post("/api/v1/speech/transcribe", content=wav(1.5))
    assert resp.status_code == 200
    assert resp.json() == {"text": "我有45万，想买一年期的理财"}


def test_transcribe_rejects_oversized_and_invalid_audio(client):
    assert client.post("/api/v1/speech/transcribe", content=b"x" * 3_000_000).status_code == 413
    assert client.post("/api/v1/speech/transcribe", content=wav(0.1)).status_code == 422


def test_transcribe_unavailable_without_model(monkeypatch):
    monkeypatch.setattr(speech, "model_installed", lambda: False)
    c = TestClient(app, headers={"X-Demo-User": "pytest_customer"})
    assert c.get("/api/v1/speech/status").json()["available"] is False
    resp = c.post("/api/v1/speech/transcribe", content=wav(1.0))
    assert resp.status_code == 503 and "download_asr_model.py" in resp.json()["detail"]


def test_transcribe_requires_known_customer():
    c = TestClient(app, headers={"X-Demo-User": "stranger"})
    assert c.post("/api/v1/speech/transcribe", content=wav(1.0)).status_code == 403
