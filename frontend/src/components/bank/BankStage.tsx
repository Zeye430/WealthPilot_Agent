"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { BANK_APP_HOME } from "@/lib/embed";
import { defineCopy, LocaleToggle, useCopy } from "@/lib/i18n";

const COPY = defineCopy({
  zh: {
    title: "从手机银行进入理财助手",
    lead: "生产中，客户不会单独登录 WealthPilot：理财助手是手机银行里的一个功能模块。左边是模拟的知岸银行 App，登录后点击「AI 理财助手」。",
    steps: [
      { t: "客户登录手机银行", d: "银行自己的账号体系与会话，WealthPilot 不参与、也拿不到银行密码。" },
      { t: "点击「AI 理财助手」模块", d: "App 请求银行后台为这次进入签发凭证。" },
      { t: "银行签发一次性凭证", d: "含客户编号、签发方与接收方、60 秒有效期、唯一编号，并用约定密钥签名。" },
      { t: "WealthPilot 核验凭证", d: "检查签名、签发方与接收方、有效期，并登记编号防止重放；首次进入自动开户。" },
      { t: "进入理财助手（嵌入模式）", d: "建立 WealthPilot 自己的会话；不显示登录与退出，只有「返回手机银行」。" },
    ],
    production: "生产中的差别",
    productionItems: [
      "App 用 WebView 打开理财助手，凭证经 JS 桥或 POST 传递，不放在地址里。",
      "银行用私钥签名（如 RS256 的 JWT），WealthPilot 只持有公钥，被攻破也无法伪造凭证。",
      "客户接口经互联网网关；理财经理与运维入口只在行内网络开放。",
    ],
    restart: "重新开始",
    otherRoles: "体验理财经理、运维看板 →",
    current: "当前步骤",
    frame: "模拟手机",
  },
  en: {
    title: "Opening the assistant from the banking app",
    lead: "In production, customers never sign in to WealthPilot separately: the assistant is one module of the bank's mobile app. On the left is a simulated Zhian Bank app. Sign in, then tap “AI wealth assistant”.",
    steps: [
      { t: "Customer signs in to the banking app", d: "The bank's own accounts and session. WealthPilot isn't involved and never sees the bank password." },
      { t: "Taps the “AI wealth assistant” module", d: "The app asks the bank's back end to issue an entry ticket." },
      { t: "Bank issues a one-time ticket", d: "Customer ID, issuer and audience, 60-second expiry and a unique ID, signed with an agreed key." },
      { t: "WealthPilot verifies the ticket", d: "Checks signature, issuer and audience, expiry, and records the ID to block replay; first-time customers are provisioned automatically." },
      { t: "Assistant opens in embedded mode", d: "WealthPilot creates its own session. No sign-in or sign-out, just “Back to banking app”." },
    ],
    production: "What changes in production",
    productionItems: [
      "The app opens the assistant in a WebView and passes the ticket via a JS bridge or POST, not in the URL.",
      "The bank signs with a private key (e.g. an RS256 JWT); WealthPilot holds only the public key, so a breach can't forge tickets.",
      "Customer APIs sit behind the internet gateway; RM and ops entry points are intranet-only.",
    ],
    restart: "Start over",
    otherRoles: "Try the RM and ops dashboards →",
    current: "Current step",
    frame: "Simulated phone",
  },
});

/**
 * Desktop demo page: the simulated banking app runs in a phone frame (same-origin iframe), with the entry steps explained on the right.
 * On a phone screen the banking app opens directly (it's already a phone, so no frame).
 */
export function BankStage() {
  const c = useCopy(COPY);
  const router = useRouter();
  const frame = useRef<HTMLIFrameElement>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(max-width: 767px)").matches) {
      router.replace(BANK_APP_HOME);
      return;
    }
    const onMessage = (e: MessageEvent) => {
      if (e.origin === window.location.origin && e.data?.type === "wp-demo-step") setStep(e.data.step);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [router]);

  function restart() {
    setStep(0);
    if (frame.current) frame.current.src = BANK_APP_HOME;
  }

  return (
    <main className="min-h-full bg-fill">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-8 py-10 lg:flex-row lg:items-start">
        <div className="mx-auto shrink-0 rounded-[52px] bg-[#0d1b2a] p-3 shadow-[0_24px_60px_rgba(10,31,61,0.25)]" aria-label={c.frame}>
          <iframe
            ref={frame}
            src={BANK_APP_HOME}
            title={c.frame}
            allow="microphone"
            className="h-[780px] w-[375px] rounded-[42px] bg-white"
          />
        </div>

        <section className="flex min-w-0 flex-1 flex-col gap-6 pt-2">
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-[28px] leading-tight font-extrabold tracking-tight">{c.title}</h1>
            <LocaleToggle className="bg-canvas" />
          </div>
          <p className="max-w-xl text-[15px] leading-7 text-ink-2">{c.lead}</p>

          <ol className="flex flex-col gap-2.5">
            {c.steps.map((s, i) => {
              const n = i + 1;
              const done = step >= n;
              const active = step + 1 === n;
              return (
                <li
                  key={s.t}
                  aria-current={active ? "step" : undefined}
                  className={`flex gap-4 rounded-card p-4 transition-colors ${active ? "bg-canvas ring-2 ring-brand" : done ? "bg-canvas" : "bg-transparent"}`}
                >
                  <span
                    className={`figures flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-extrabold ${
                      done ? "bg-ok text-white" : active ? "bg-brand text-on-brand" : "bg-line text-ink-2"
                    }`}
                  >
                    {done ? "✓" : n}
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="font-bold">{s.t}</span>
                    <span className="text-sm leading-6 text-ink-2">{s.d}</span>
                  </span>
                </li>
              );
            })}
          </ol>

          <div className="rounded-card bg-canvas p-5">
            <h2 className="text-[15px] font-extrabold">{c.production}</h2>
            <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-sm leading-6 text-ink-2">
              {c.productionItems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-sm font-bold">
            <button type="button" onClick={restart} className="rounded-full bg-navy px-5 py-2.5 text-white">
              {c.restart}
            </button>
            <Link href="/login" className="text-brand hover:underline">
              {c.otherRoles}
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
