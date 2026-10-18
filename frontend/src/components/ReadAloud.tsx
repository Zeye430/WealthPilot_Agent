"use client";

import { useEffect, useState } from "react";

/**
 * 朗读回答：使用浏览器 / 系统自带的中文语音合成（免费、离线）。
 * 只读文字结论；表格、卡片和图表读不出来，结尾提示「详细内容请看屏幕」。风险提示仍以文字为准。
 */
export function ReadAloud({ text, hasBlocks }: { text: string; hasBlocks: boolean }) {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    // 首次渲染在服务端，挂载后才能判断浏览器能力
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    };
  }, []);

  if (!supported || !text.trim()) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    synth.cancel(); // 同一时间只朗读一条
    const utterance = new SpeechSynthesisUtterance(speakable(text, hasBlocks));
    utterance.lang = "zh-CN";
    const voice = synth.getVoices().find((v) => v.lang.replace("_", "-").startsWith("zh-CN"));
    if (voice) utterance.voice = voice;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    synth.speak(utterance);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={speaking}
      className="text-xs text-ink-3 underline-offset-4 hover:text-brand hover:underline"
    >
      {speaking ? "停止朗读" : "朗读"}
    </button>
  );
}

/** 去掉 Markdown 标记、表格和资料编号，转成适合朗读的文字。 */
export function speakable(markdown: string, hasBlocks: boolean): string {
  const lines = markdown
    .split("\n")
    .filter((line) => !line.trim().startsWith("|")) // 表格
    .map((line) =>
      line
        .replace(/^\s*#{1,6}\s*/, "")
        .replace(/^\s*>\s?/, "")
        .replace(/^\s*[-*]\s+/, "")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // 链接只读文字
        .replace(/\[[A-Z]{1,3}[-\w#]*\]/g, "") // 资料编号，如 [K17]、[ZA-F03#四]
        .replace(/[*_`~]/g, ""),
    );
  const text = lines.join("\n").replace(/\n{2,}/g, "\n").trim();
  return hasBlocks ? `${text}\n详细内容请看屏幕。` : text;
}
