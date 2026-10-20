"use client";

import { useEffect, useState } from "react";

import { defineCopy, useCopy } from "@/lib/i18n";

const COPY = defineCopy({
  zh: { read: "朗读", stop: "停止朗读", seeScreen: "详细内容请看屏幕。" },
  en: { read: "Read aloud", stop: "Stop", seeScreen: "See the screen for details." },
});

/**
 * Read replies aloud with the browser's / system's built-in speech synthesis (free, offline).
 * Reads only the text; tables, cards and charts can't be read, so it ends with "see the screen for details". Risk disclosures remain authoritative in text.
 */
export function ReadAloud({ text, hasBlocks }: { text: string; hasBlocks: boolean }) {
  const c = useCopy(COPY);
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    // The first render happens on the server; browser capabilities are known only after mounting
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
    synth.cancel(); // read one reply at a time
    // The voice follows the reply's language: Chinese if it contains Chinese, otherwise English
    const lang = /[\u4e00-\u9fff]/.test(text) ? "zh-CN" : "en-US";
    const utterance = new SpeechSynthesisUtterance(speakable(text, hasBlocks ? c.seeScreen : null));
    utterance.lang = lang;
    const voice = synth.getVoices().find((v) => v.lang.replace("_", "-").startsWith(lang));
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
      className="h-8 self-start rounded-full bg-fill px-3 text-xs font-semibold text-ink hover:bg-line"
    >
      {speaking ? c.stop : c.read}
    </button>
  );
}

/** Strip Markdown, tables and source IDs to get text suitable for reading aloud. */
export function speakable(markdown: string, suffix: string | null): string {
  const lines = markdown
    .split("\n")
    .filter((line) => !line.trim().startsWith("|")) // tables
    .map((line) =>
      line
        .replace(/^\s*#{1,6}\s*/, "")
        .replace(/^\s*>\s?/, "")
        .replace(/^\s*[-*]\s+/, "")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // read only the link text
        .replace(/\[[A-Z]{1,3}[-\w#]*\]/g, "") // source IDs such as [K17] or [ZA-F03#<section>]
        .replace(/[*_`~]/g, ""),
    );
  const text = lines.join("\n").replace(/\n{2,}/g, "\n").trim();
  return suffix ? `${text}\n${suffix}` : text;
}
