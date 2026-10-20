"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui";
import { ApiError, speechStatus, transcribeSpeech } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import { PcmRecorder, recordingSupported } from "@/lib/recorder";

const COPY = defineCopy({
  zh: {
    micDenied: "无法使用麦克风：请在浏览器设置中允许麦克风权限。",
    failed: "识别失败，请重试。",
    recording: "正在录音",
    tapToStop: "再点麦克风结束",
    release: "松开结束",
    privacy: "录音在本行服务器转成文字，不发给第三方，不保存",
    sep: "；",
    transcribing: "正在识别…",
    cancel: "取消",
    close: "关闭",
    stop: "结束录音",
    start: "按住说话",
  },
  en: {
    micDenied: "Microphone blocked. Allow microphone access in your browser settings.",
    failed: "Couldn't transcribe. Please try again.",
    recording: "Recording",
    tapToStop: "Tap the mic to stop",
    release: "Release to stop",
    privacy: "Transcribed on our own server, never shared or stored",
    sep: ". ",
    transcribing: "Transcribing…",
    cancel: "Cancel",
    close: "Close",
    stop: "Stop recording",
    start: "Hold to talk",
  },
});

type Phase = "idle" | "recording" | "transcribing";

// A short press (under this duration) switches to tap-to-start / tap-to-stop; a long press stops on release
const HOLD_MS = 350;

/**
 * Voice input: hold to talk, release to stop (or tap to start, tap again to stop).
 * The recognized text goes into the input box for the customer to confirm or edit before sending; purchases, reminders, etc. still need a tap in the UI.
 */
export function VoiceInput({ onText, disabled }: { onText: (text: string) => void; disabled?: boolean }) {
  const c = useCopy(COPY);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [maxSeconds, setMaxSeconds] = useState(60);
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [toggleMode, setToggleMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<PcmRecorder | null>(null);
  const pressedAt = useRef(0);
  // Track the press in a ref: opening the mic is async (and needs permission the first time), so the finger may have lifted before recording starts
  const pressing = useRef(false);

  useEffect(() => {
    // Hide the mic button if the browser can't record or the backend has no recognition model
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
    // finish only depends on the ref, so it needn't be a dependency
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
      // Already released when recording actually starts (short press, or released during the permission prompt): switch to tap-to-stop
      if (!pressing.current) setToggleMode(true);
    } catch {
      setError(c.micDenied);
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
      setError(e instanceof ApiError ? e.message : c.failed);
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
      setToggleMode(true); // short press: keep recording until the next tap
    } else {
      await finish(); // long press: stop on release
    }
  }

  if (available === false || available === null) return null;

  const recording = phase === "recording";
  return (
    <>
      {(recording || phase === "transcribing" || error) && (
        <div
          role="status"
          className="absolute inset-x-4 bottom-full mb-2 flex items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-3 text-sm shadow-[0_4px_24px_rgba(10,31,61,0.12)] lg:inset-x-12"
        >
          {error ? (
            <span className="text-danger">{error}</span>
          ) : recording ? (
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-danger" />
              <span className="font-bold">{c.recording}</span>
              <span className="figures font-bold">{formatSeconds(elapsed)}</span>
              <span className="text-xs text-ink-3">
                {toggleMode ? c.tapToStop : c.release}
                {c.sep}
                {c.privacy}
              </span>
            </span>
          ) : (
            <span className="text-ink-2">{c.transcribing}</span>
          )}
          {recording && (
            <button type="button" onClick={cancel} className="shrink-0 text-xs font-semibold text-ink-3 hover:text-ink">
              {c.cancel}
            </button>
          )}
          {error && (
            <button type="button" onClick={() => setError(null)} className="shrink-0 text-xs font-semibold text-ink-3 hover:text-ink">
              {c.close}
            </button>
          )}
        </div>
      )}
      <button
        type="button"
        aria-label={recording ? c.stop : c.start}
        aria-pressed={recording}
        disabled={disabled || phase === "transcribing"}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          // Sliding off the button during a long press counts as release
          if (pressing.current) onPointerUp();
        }}
        onContextMenu={(e) => e.preventDefault()}
        className={`flex h-13 w-13 shrink-0 touch-none items-center justify-center rounded-full select-none disabled:opacity-40 ${
          recording ? "bg-danger text-white" : "bg-brand text-on-brand hover:bg-brand-strong"
        }`}
      >
        <Icon name="mic" />
      </button>
    </>
  );
}

function formatSeconds(s: number) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

