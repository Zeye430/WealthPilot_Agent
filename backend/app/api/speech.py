"""语音转文字 API：前端上传 WAV，返回识别文字，由客户确认后再发送。音频不保存。"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user, get_customer_id
from app.auth.service import CurrentUser
from app.core.config import get_settings
from app.core.i18n import L
from app.core.ratelimit import speech_limit
from app.speech.recognizer import AudioError, decode_wav, get_recognizer, model_installed

router = APIRouter(prefix="/api/v1/speech", tags=["speech"])

# 16 kHz × 16 位 × 单声道 ≈ 32 KB/秒，留出 WAV 头的余量
BYTES_PER_SECOND = 32000


@router.get("/status")
def status():
    return {"available": model_installed(), "max_seconds": get_settings().asr_max_seconds}


@router.post("/transcribe")
async def transcribe(
    request: Request,
    _customer: str = Depends(get_customer_id),
    user: CurrentUser = Depends(get_current_user),
):
    speech_limit(user)
    if not model_installed():
        raise HTTPException(
            status_code=503,
            detail=L("语音识别模型未安装：", "Speech model not installed: ")
            + L("请在 backend/ 下运行 ", "in backend/, run ")
            + "uv run python ../scripts/download_asr_model.py",
        )
    max_seconds = get_settings().asr_max_seconds
    data = await request.body()
    if len(data) > (max_seconds + 1) * BYTES_PER_SECOND:
        raise HTTPException(
            status_code=413,
            detail=L(
                f"录音超过 {max_seconds} 秒，请分段说",
                f"Recording is over {max_seconds} seconds. Please say it in shorter parts.",
            ),
        )
    try:
        samples = decode_wav(data, max_seconds)
    except AudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    text = get_recognizer().transcribe(samples)
    if not text:
        raise HTTPException(
            status_code=422,
            detail=L(
                "没有听清，请靠近麦克风再说一次",
                "Didn't catch that. Move closer to the mic and try again.",
            ),
        )
    return {"text": text}
