"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Avatar, Button } from "@/components/ui";
import { ApiError, getLoginConfig, login, type LoginConfig } from "@/lib/api";
import { defineCopy, LocaleToggle, useCopy, stripFictional, initial } from "@/lib/i18n";

const COPY = defineCopy({
  zh: {
    tagline: "知岸银行（虚构）智能理财助手",
    welcome: "欢迎回来",
    pick: "选择演示账号",
    roles: { customer: "客户", rm: "理财经理", ops: "运维值班" },
    username: "账号",
    password: "密码",
    accessCode: "访问码",
    signIn: "登录",
    signingIn: "登录中…",
    failed: "登录失败，请重试。",
    noServer: "无法连接服务器",
    demo: "作品集演示系统：机构、产品与客户均为虚构；买入流程只到确认页，不会真实下单。",
  },
  en: {
    tagline: "AI wealth assistant for Zhian Bank (fictional)",
    welcome: "Welcome back",
    pick: "Choose a demo account",
    roles: { customer: "Customer", rm: "Relationship manager", ops: "Operations" },
    username: "Username",
    password: "Password",
    accessCode: "Access code",
    signIn: "Sign in",
    signingIn: "Signing in…",
    failed: "Sign-in failed. Please try again.",
    noServer: "Can't reach the server",
    demo: "Portfolio demo: the bank, products and customers are fictional. Purchases stop at the confirmation step.",
  },
});

/** 登录页：账号密码登录；公开演示时需要访问码。会话保存在 httpOnly Cookie 中。 */
export function LoginForm({ next }: { next: string | null }) {
  const c = useCopy(COPY);
  const router = useRouter();
  const [config, setConfig] = useState<LoginConfig | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLoginConfig()
      .then(setConfig)
      .catch((e) => setError(e instanceof ApiError ? e.message : c.noServer));
  }, [c.noServer]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(username, password, accessCode);
      // 只允许站内跳转，防止登录后被重定向到外部网站
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
      const home = { rm: "/rm", ops: "/ops" } as Record<string, string>;
      router.replace(home[user.role] ?? safeNext ?? "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : c.failed);
      setBusy(false);
    }
  }

  const inputClass =
    "h-13 w-full rounded-full bg-fill px-5 text-[15px] outline-none placeholder:text-ink-3 focus:ring-2 focus:ring-brand";

  return (
    <main className="flex min-h-full flex-col bg-canvas">
      <div className="flex justify-end px-5 pt-4">
        <LocaleToggle />
      </div>
      <div className="flex flex-1 items-start justify-center px-5 pt-6 pb-12 sm:items-center sm:pt-0">
        <div className="w-full max-w-sm">
          <p className="text-[28px] font-extrabold tracking-tight">WealthPilot</p>
          <p className="mt-1 text-sm text-ink-3">{c.tagline}</p>
          <h1 className="mt-8 text-[22px] font-extrabold">{c.welcome}</h1>

          <form onSubmit={submit} className="mt-5 flex flex-col gap-4">
            {config && config.demo_accounts.length > 0 && (
              <fieldset>
                <legend className="text-xs font-bold text-ink-3">{c.pick}</legend>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {config.demo_accounts.map((a) => (
                    <button
                      key={a.username}
                      type="button"
                      onClick={() => setUsername(a.username)}
                      aria-pressed={username === a.username}
                      className={`flex items-center gap-2.5 rounded-2xl px-3 py-2.5 text-left text-sm transition-colors ${
                        username === a.username ? "bg-brand-soft ring-2 ring-brand" : "bg-fill hover:bg-line"
                      }`}
                    >
                      <Avatar text={initial(a.display_name)} tone={a.role === "customer" ? "brand" : "navy"} />
                      <span className="min-w-0">
                        <span className="block truncate font-bold">{stripFictional(a.display_name)}</span>
                        <span className="text-xs text-ink-3">{c.roles[a.role]}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </fieldset>
            )}

            <label className="sr-only" htmlFor="username">
              {c.username}
            </label>
            <input id="username" autoComplete="username" placeholder={c.username} value={username} onChange={(e) => setUsername(e.target.value)} className={inputClass} required />
            <label className="sr-only" htmlFor="password">
              {c.password}
            </label>
            <input id="password" type="password" autoComplete="current-password" placeholder={c.password} value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} required />
            {config?.access_code_required && (
              <>
                <label className="sr-only" htmlFor="access-code">
                  {c.accessCode}
                </label>
                <input id="access-code" placeholder={c.accessCode} value={accessCode} onChange={(e) => setAccessCode(e.target.value)} className={inputClass} required />
              </>
            )}

            {error && (
              <p role="alert" className="rounded-2xl bg-danger-soft px-4 py-2.5 text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" disabled={busy} className="w-full">
              {busy ? c.signingIn : c.signIn}
            </Button>
            {config?.hint && <p className="text-center text-xs text-ink-3">{config.hint}</p>}
          </form>
          <p className="mt-8 text-xs leading-5 text-ink-3">{c.demo}</p>
        </div>
      </div>
    </main>
  );
}
