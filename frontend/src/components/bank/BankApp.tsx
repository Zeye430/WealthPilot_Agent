"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, bankApi, getLoginConfig, type BankHome, type LoginConfig } from "@/lib/api";
import { notifyDemoStep, setEmbedded } from "@/lib/embed";
import { defineCopy, intlLocale, LocaleToggle, useCopy, useLocale } from "@/lib/i18n";

/**
 * 模拟的「知岸银行」手机银行（演示用）：代表银行自己的 App，不属于 WealthPilot。
 * 客户在这里用银行账号登录；「AI 理财助手」是首页上的一个功能模块，点击后由银行后台签发一次性凭证，
 * 打开 WealthPilot 并免密进入。两边不共享账号、密码与会话。
 * 配色刻意与 WealthPilot 不同（深青绿），提醒这是另一个系统。
 */

const BANK = "#0b5f5a";
const BANK_DARK = "#07413d";
const BANK_SOFT = "#e3f1ef";

const COPY = defineCopy({
  zh: {
    bank: "知岸银行",
    app: "手机银行",
    simNote: "演示：模拟的银行 App，账号体系与 WealthPilot 相互独立",
    username: "用户名",
    password: "登录密码",
    login: "登录",
    loggingIn: "登录中…",
    pick: "演示客户",
    accessCode: "访问码",
    greeting: (name: string) => `您好，${name}`,
    total: "总资产（元）",
    show: "显示金额",
    hide: "隐藏金额",
    demand: "活期",
    time: "定期",
    wealth: "理财",
    services: [
      { key: "transfer", label: "转账汇款" },
      { key: "receive", label: "收款" },
      { key: "detail", label: "账户明细" },
      { key: "card", label: "信用卡" },
      { key: "fund", label: "基金" },
      { key: "bills", label: "生活缴费" },
      { key: "loan", label: "贷款" },
      { key: "ai", label: "AI 理财助手" },
    ],
    new: "新",
    bannerTitle: "AI 理财助手",
    bannerText: "理财规划、产品答疑、按需匹配，随时问",
    bannerCta: "去问问",
    opening: "正在打开…",
    notInDemo: "演示环境：仅「AI 理财助手」可用",
    tabs: ["首页", "理财", "生活", "我的"],
    logout: "退出",
    failed: "操作失败，请重试",
  },
  en: {
    bank: "Zhian Bank",
    app: "Mobile banking",
    simNote: "Demo: a simulated banking app with its own accounts, separate from WealthPilot",
    username: "Username",
    password: "Password",
    login: "Sign in",
    loggingIn: "Signing in…",
    pick: "Demo customers",
    accessCode: "Access code",
    greeting: (name: string) => `Hello, ${name}`,
    total: "Total assets (CNY)",
    show: "Show amounts",
    hide: "Hide amounts",
    demand: "Checking",
    time: "Time deposits",
    wealth: "Wealth",
    services: [
      { key: "transfer", label: "Transfer" },
      { key: "receive", label: "Receive" },
      { key: "detail", label: "Statements" },
      { key: "card", label: "Credit card" },
      { key: "fund", label: "Funds" },
      { key: "bills", label: "Bills" },
      { key: "loan", label: "Loans" },
      { key: "ai", label: "AI wealth assistant" },
    ],
    new: "New",
    bannerTitle: "AI wealth assistant",
    bannerText: "Planning, product questions and needs-based matching, anytime",
    bannerCta: "Ask now",
    opening: "Opening…",
    notInDemo: "Demo: only the AI wealth assistant is available",
    tabs: ["Home", "Wealth", "Life", "Me"],
    logout: "Sign out",
    failed: "Something went wrong. Please try again.",
  },
});

const DEMO_CUSTOMERS = [
  { username: "wang", zh: "王先生", en: "Mr. Wang" },
  { username: "chen", zh: "陈女士", en: "Ms. Chen" },
];

export function BankApp() {
  const [home, setHome] = useState<BankHome | null>(null);
  const [checked, setChecked] = useState(false);

  const load = useCallback(async () => {
    try {
      setHome(await bankApi.home());
    } catch {
      setHome(null);
    } finally {
      setChecked(true);
    }
  }, []);

  useEffect(() => {
    // 回到手机银行：理财助手的嵌入标记随之清除
    setEmbedded(false);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  if (!checked) return <div className="h-full bg-[#f2f4f5]" />;
  return home ? <BankHomeView home={home} onLogout={() => setHome(null)} /> : <BankLogin onDone={load} />;
}

function BankLogin({ onDone }: { onDone: () => void }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const [username, setUsername] = useState("wang");
  const [password, setPassword] = useState("");
  const [accessCode, setAccessCode] = useState("");
  // 与 WealthPilot 登录页同一份配置：是否需要访问码、演示密码提示（公开部署时由服务器配置决定）
  const [config, setConfig] = useState<LoginConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLoginConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await bankApi.login(username, password, accessCode);
      notifyDemoStep(1);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : c.failed);
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-full flex-col bg-white">
      <div className="flex flex-col gap-1 px-6 pt-14 pb-10 text-white" style={{ background: `linear-gradient(160deg, ${BANK}, ${BANK_DARK})` }}>
        <div className="flex items-center justify-between">
          <BankLogo />
          <LocaleToggle className="bg-white/15 text-white hover:bg-white/25" />
        </div>
        <p className="mt-8 text-[26px] font-extrabold tracking-tight">{c.bank}</p>
        <p className="text-sm text-white/75">{c.app}</p>
      </div>
      <form onSubmit={submit} className="-mt-5 flex flex-1 flex-col gap-4 rounded-t-3xl bg-white px-6 pt-7">
        <fieldset>
          <legend className="text-xs font-bold text-[#5c6b6a]">{c.pick}</legend>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {DEMO_CUSTOMERS.map((d) => (
              <button
                key={d.username}
                type="button"
                aria-pressed={username === d.username}
                onClick={() => setUsername(d.username)}
                className="rounded-2xl px-3 py-2.5 text-sm font-bold"
                style={username === d.username ? { background: BANK_SOFT, color: BANK, boxShadow: `inset 0 0 0 2px ${BANK}` } : { background: "#f2f4f5" }}
              >
                {d[locale]}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="sr-only" htmlFor="bank-username">
          {c.username}
        </label>
        <input id="bank-username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder={c.username} autoComplete="username" className="h-12 rounded-xl border border-[#d9e1e0] px-4 text-[15px] outline-none focus:border-[#0b5f5a]" />
        <label className="sr-only" htmlFor="bank-password">
          {c.password}
        </label>
        <input id="bank-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={c.password} autoComplete="current-password" className="h-12 rounded-xl border border-[#d9e1e0] px-4 text-[15px] outline-none focus:border-[#0b5f5a]" required />
        {config?.access_code_required && (
          <>
            <label className="sr-only" htmlFor="bank-access-code">
              {c.accessCode}
            </label>
            <input id="bank-access-code" value={accessCode} onChange={(e) => setAccessCode(e.target.value)} placeholder={c.accessCode} className="h-12 rounded-xl border border-[#d9e1e0] px-4 text-[15px] outline-none focus:border-[#0b5f5a]" required />
          </>
        )}
        {error && (
          <p role="alert" className="text-sm text-[#b42318]">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy} className="h-12 rounded-xl text-[15px] font-bold text-white disabled:opacity-50" style={{ background: BANK }}>
          {busy ? c.loggingIn : c.login}
        </button>
        {config?.hint && <p className="text-center text-xs text-[#5c6b6a]">{config.hint}</p>}
        <p className="mt-auto pb-6 text-center text-[11px] leading-4 text-[#8a9796]">{c.simNote}</p>
      </form>
    </main>
  );
}

function BankHomeView({ home, onLogout }: { home: BankHome; onLogout: () => void }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const [visible, setVisible] = useState(true);
  const [opening, setOpening] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const money = (v: number) =>
    visible ? v.toLocaleString(intlLocale(locale), { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "****";

  async function openAssistant() {
    if (opening) return;
    setOpening(true);
    notifyDemoStep(2);
    try {
      const { ticket } = await bankApi.ticket();
      notifyDemoStep(3);
      // 生产中：App 用 WebView 打开理财助手的 H5，凭证经 JS 桥或 POST 传递，不放在地址里
      // 整页跳转：模拟 App 新开一个页面，理财助手不沿用手机银行的页面状态
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(`/app-entry?ticket=${encodeURIComponent(ticket)}`);
    } catch (e) {
      setOpening(false);
      showToast(e instanceof ApiError ? e.message : c.failed);
    }
  }

  function showToast(text: string) {
    setToast(text);
    setTimeout(() => setToast(null), 1800);
  }

  async function logout() {
    await bankApi.logout().catch(() => undefined);
    onLogout();
  }

  return (
    <div className="relative flex h-full flex-col bg-[#f2f4f5]">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <header className="px-5 pt-12 pb-20 text-white" style={{ background: `linear-gradient(160deg, ${BANK}, ${BANK_DARK})` }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <BankLogo small />
              <span className="text-[17px] font-extrabold">{c.bank}</span>
            </div>
            <div className="flex items-center gap-2">
              <LocaleToggle className="h-8 bg-white/15 px-3 text-xs text-white hover:bg-white/25" />
              <button type="button" onClick={logout} className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold hover:bg-white/25">
                {c.logout}
              </button>
            </div>
          </div>
          <p className="mt-5 text-[15px] font-semibold">{c.greeting(home.name.replace(/\s*[（(](虚构|fictional)[）)]$/, ""))}</p>
          <p className="mt-0.5 text-xs text-white/75">
            {home.tier} · {home.card} ···· {home.card_tail}
          </p>
        </header>

        <section className="-mt-14 mx-4 rounded-3xl bg-white p-5 shadow-[0_8px_24px_rgba(7,65,61,0.10)]">
          <div className="flex items-center gap-2 text-xs text-[#5c6b6a]">
            {c.total}
            <button type="button" onClick={() => setVisible((v) => !v)} aria-label={visible ? c.hide : c.show} className="text-[#5c6b6a]">
              <EyeIcon open={visible} />
            </button>
          </div>
          <p className="mt-1 text-[30px] font-extrabold tracking-tight tabular-nums">{money(home.total)}</p>
          <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-[#edf1f0] pt-3 text-xs">
            {[
              [c.demand, home.demand_deposit],
              [c.time, home.time_deposit],
              [c.wealth, home.wealth],
            ].map(([label, v]) => (
              <div key={label as string}>
                <dt className="text-[#5c6b6a]">{label}</dt>
                <dd className="mt-0.5 font-bold tabular-nums">{money(v as number)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mx-4 mt-3 grid grid-cols-4 gap-y-4 rounded-3xl bg-white px-2 py-5">
          {c.services.map((s) => {
            const ai = s.key === "ai";
            return (
              <button
                key={s.key}
                type="button"
                onClick={ai ? openAssistant : () => showToast(c.notInDemo)}
                className="relative flex flex-col items-center gap-1.5 text-[12px] font-semibold text-[#1d2b2a]"
              >
                <span
                  className="flex h-11 w-11 items-center justify-center rounded-2xl"
                  style={ai ? { background: BANK, color: "white" } : { background: BANK_SOFT, color: BANK }}
                >
                  <ServiceIcon name={s.key} />
                </span>
                <span className="text-center leading-tight">{s.label}</span>
                {ai && (
                  <span className="absolute -top-1.5 right-2 rounded-full bg-[#e8590c] px-1.5 text-[10px] font-bold text-white">{c.new}</span>
                )}
              </button>
            );
          })}
        </section>

        <button
          type="button"
          onClick={openAssistant}
          className="mx-4 mt-3 mb-5 flex w-[calc(100%-2rem)] items-center justify-between gap-3 rounded-3xl p-5 text-left text-white"
          style={{ background: `linear-gradient(120deg, ${BANK_DARK}, ${BANK})` }}
        >
          <span className="flex flex-col gap-1">
            <span className="text-[16px] font-extrabold">{c.bannerTitle}</span>
            <span className="text-xs leading-5 text-white/80">{c.bannerText}</span>
          </span>
          <span className="shrink-0 rounded-full bg-white px-4 py-2 text-sm font-bold" style={{ color: BANK }}>
            {opening ? c.opening : c.bannerCta}
          </span>
        </button>
      </div>

      <nav className="grid h-[62px] shrink-0 grid-cols-4 border-t border-[#e3e8e7] bg-white text-[11px]">
        {c.tabs.map((t, i) => (
          <button
            key={t}
            type="button"
            onClick={() => i !== 0 && showToast(c.notInDemo)}
            className="flex flex-col items-center justify-center gap-1 font-semibold"
            style={{ color: i === 0 ? BANK : "#8a9796" }}
          >
            <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ background: i === 0 ? BANK : "transparent" }} />
            {t}
          </button>
        ))}
      </nav>

      {toast && (
        <p role="status" className="absolute bottom-20 left-1/2 -translate-x-1/2 rounded-full bg-[#1d2b2a]/90 px-4 py-2 text-xs whitespace-nowrap text-white">
          {toast}
        </p>
      )}
    </div>
  );
}

function BankLogo({ small = false }: { small?: boolean }) {
  const size = small ? 28 : 40;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden>
      <rect width="40" height="40" rx="11" fill="white" fillOpacity="0.16" />
      <path d="M9 26c5-9 17-9 22 0" stroke="white" strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d="M13 30h14" stroke="#f2c14e" strokeWidth="3" strokeLinecap="round" />
      <circle cx="20" cy="14" r="3.5" fill="#f2c14e" />
    </svg>
  );
}

function EyeIcon({ open }: { open: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
      {open ? <circle cx="12" cy="12" r="3" /> : <path d="M4 4l16 16" />}
    </svg>
  );
}

function ServiceIcon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    transfer: <path d="M4 8h13l-3-3M20 16H7l3 3" />,
    receive: <path d="M12 4v12m0 0l-4-4m4 4l4-4M5 20h14" />,
    detail: <path d="M7 4h10v16H7zM10 9h4M10 13h4" />,
    card: <path d="M3 7h18v10H3zM3 11h18" />,
    fund: <path d="M4 18l5-6 4 3 7-9" />,
    bills: <path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 9h6M9 13h6" />,
    loan: <path d="M12 3v18M16 7h-5.5a2.5 2.5 0 0 0 0 5h3a2.5 2.5 0 0 1 0 5H8" />,
    ai: <path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9z" />,
  };
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {paths[name]}
    </svg>
  );
}
