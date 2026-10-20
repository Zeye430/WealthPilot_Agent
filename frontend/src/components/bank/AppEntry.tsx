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
 * Banking-app entry page: reads the one-time ticket from the app, exchanges it with the WealthPilot backend for a session, then opens the assistant.
 * The ticket is removed from the address bar right away (kept out of history); it expires in 60 s and works only once.
 */
export function AppEntry() {
  const c = useCopy(COPY);
  const { setLocale } = useLocale();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // effects run twice in development, and the ticket works only once
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
