"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, speechStatus, transcribeSpeech } from "@/lib/api";
import { PcmRecorder, recordingSupported } from "@/lib/recorder";

type Phase = "idle" | "recording" | "transcribing";

// 短按（不足此时长）进入「点击开始 / 再点结束」模式；长按则松开即结束
const HOLD_MS = 350;

/**
 * 语音输入：按住说话、松开结束（或点一下开始、再点一下结束）。
 * 识别结果填入输入框，由客户确认或修改后再发送；买入、提醒等操作仍需在界面上点击确认。
 */
export function VoiceInput({ onText, disabled }: { onText: (text: string) => void; disabled?: boolean }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [maxSeconds, setMaxSeconds] = useState(60);
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [toggleMode, setToggleMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<PcmRecorder | null>(null);
  const pressedAt = useRef(0);
  // 按压状态用 ref 记录：开启麦克风是异步的（首次还要授权），开始录音时手指可能早已松开
  const pressing = useRef(false);

  useEffect(() => {
    // 浏览器不支持录音、或后端未安装识别模型时，不显示麦克风按钮
    const status = recordingSupported()
      ? speechStatus()
      : Promise.resolve({ available: false, max_seconds: 60 });
    status
      .then((s) => {
        setAvailable(s.available);
        setMaxSeconds(s.max_seconds);
      })
      .catch(() => setAvailable(false));
  }, []);

  useEffect(() => {
    if (phase !== "recording") return;
    const started = Date.now();
    const timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      setElapsed(seconds);
      if (seconds >= maxSeconds) finish();
    }, 250);
    return () => clearInterval(timer);
    // finish 只依赖 ref，无需加入依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, maxSeconds]);

  async function begin() {
    setError(null);
    setElapsed(0);
    const r = new PcmRecorder();
    try {
      await r.start();
      recorder.current = r;
      setPhase("recording");
      // 录音真正开始时已经松开（短按，或授权弹窗期间松手）：改为「再点一下结束」
      if (!pressing.current) setToggleMode(true);
    } catch {
      setError("无法使用麦克风：请在浏览器设置中允许麦克风权限。");
    }
  }

  async function finish() {
    const r = recorder.current;
    recorder.current = null;
    setToggleMode(false);
    if (!r) return;
    setPhase("transcribing");
    try {
      const wav = await r.stop();
      if (wav) onText((await transcribeSpeech(wav)).text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "识别失败，请重试。");
    } finally {
      setPhase("idle");
    }
  }

  function cancel() {
    recorder.current?.cancel();
    recorder.current = null;
    setToggleMode(false);
    setPhase("idle");
  }

  async function onPointerDown() {
    if (disabled || phase === "transcribing") return;
    if (recorder.current) {
      if (toggleMode) await finish();
      return;
    }
    pressing.current = true;
    pressedAt.current = Date.now();
    await begin();
  }

  async function onPointerUp() {
    const wasPressing = pressing.current;
    pressing.current = false;
    if (!wasPressing || !recorder.current || toggleMode) return;
    if (Date.now() - pressedAt.current < HOLD_MS) {
      setToggleMode(true); // 短按：继续录音，等再点一下
    } else {
      await finish(); // 长按：松开即结束
    }
  }

  if (available === false || available === null) return null;

  const recording = phase === "recording";
  return (
    <>
      {(recording || phase === "transcribing" || error) && (
        <div role="status" className="absolute inset-x-0 bottom-full mb-2 flex items-center justify-between gap-3 rounded-sm border border-rule bg-surface px-3 py-2 text-sm shadow-sm">
          {error ? (
            <span className="text-danger">{error}</span>
          ) : recording ? (
            <span className="flex items-center gap-2">
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-danger" />
              正在录音 <span className="figures">{formatSeconds(elapsed)}</span>
              <span className="text-xs text-ink-3">
                {toggleMode ? "再点麦克风结束" : "松开结束"}，录音只在本机转成文字，不保存
              </span>
            </span>
          ) : (
            <span className="text-ink-2">正在识别…</span>
          )}
          {recording && (
            <button type="button" onClick={cancel} className="text-xs text-ink-3 underline underline-offset-4">
              取消
            </button>
          )}
          {error && (
            <button type="button" onClick={() => setError(null)} className="text-xs text-ink-3 underline underline-offset-4">
              关闭
            </button>
          )}
        </div>
      )}
      <button
        type="button"
        aria-label={recording ? "结束录音" : "语音输入"}
        aria-pressed={recording}
        disabled={disabled || phase === "transcribing"}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          // 长按时手指滑出按钮也视为松开
          if (pressing.current) onPointerUp();
        }}
        onContextMenu={(e) => e.preventDefault()}
        className={`flex h-10 w-10 shrink-0 touch-none items-center justify-center rounded-sm border select-none disabled:opacity-40 ${
          recording ? "border-danger bg-danger text-surface" : "border-rule text-ink-2 hover:border-brand hover:text-brand"
        }`}
      >
        <MicIcon />
      </button>
    </>
  );
}

function formatSeconds(s: number) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </svg>
  );
}
