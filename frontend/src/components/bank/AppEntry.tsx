"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui";
import { ApiError, enterFromBankApp } from "@/lib/api";
import { BANK_APP_HOME, notifyDemoStep, setEmbedded } from "@/lib/embed";
import { defineCopy, useCopy, useLocale } from "@/lib/i18n";

const COPY = defineCopy({
  zh: { entering: "正在进入 AI 理财助手…", failed: "无法进入", back: "返回手机银行" },
  en: { entering: "Opening the AI wealth assistant…", failed: "Couldn't open the assistant", back: "Back to banking app" },
});

/**
 * 手机银行进入页：读取 App 传来的一次性凭证，向 WealthPilot 后端换取会话，然后进入理财助手。
 * 凭证随即从地址栏移除（不留在浏览记录中）；凭证本身 60 秒过期、只能用一次。
 */
export function AppEntry() {
  const c = useCopy(COPY);
  const { setLocale } = useLocale();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // 开发模式下 effect 会执行两次，凭证只能用一次
    started.current = true;
    const ticket = new URLSearchParams(window.location.search).get("ticket");
    window.history.replaceState(null, "", "/app-entry");
    if (!ticket) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError("missing ticket");
      return;
    }
    notifyDemoStep(4);
    enterFromBankApp(ticket)
      .then((res) => {
        setEmbedded(true);
        setLocale(res.locale);
        notifyDemoStep(5);
        router.replace("/");
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [router, setLocale]);

  return (
    <main className="flex min-h-full flex-col items-center justify-center gap-5 bg-canvas px-6 text-center">
      {error ? (
        <>
          <p className="text-lg font-extrabold">{c.failed}</p>
          <p className="max-w-xs text-sm leading-6 text-ink-2">{error}</p>
          <Button onClick={() => window.location.assign(BANK_APP_HOME)}>{c.back}</Button>
        </>
      ) : (
        <>
          <span aria-hidden className="h-10 w-10 animate-spin rounded-full border-4 border-brand-soft border-t-brand" />
          <p className="text-[15px] font-semibold text-ink-2">{c.entering}</p>
        </>
      )}
    </main>
  );
}
