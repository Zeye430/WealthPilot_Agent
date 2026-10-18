"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, getLoginConfig, login, type LoginConfig } from "@/lib/api";

const ROLE_LABEL = { customer: "客户", rm: "理财经理" } as const;

/** 登录页：账号密码登录；公开演示时需要访问码。会话保存在 httpOnly Cookie 中。 */
export function LoginForm({ next }: { next: string | null }) {
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
      .catch((e) => setError(e instanceof ApiError ? e.message : "无法连接服务器"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(username, password, accessCode);
      // 只允许站内跳转，防止登录后被重定向到外部网站
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
      router.replace(user.role === "rm" ? "/rm" : (safeNext ?? "/"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请重试。");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <p className="font-serif text-2xl font-bold text-brand">WealthPilot</p>
        <p className="mt-1 text-sm text-ink-2">理财助手（演示版）</p>

        <form onSubmit={submit} className="mt-8 space-y-4 rounded-sm border border-rule bg-surface px-5 py-6">
          {config && config.demo_accounts.length > 0 && (
            <fieldset>
              <legend className="text-xs text-ink-2">选择演示账号</legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {config.demo_accounts.map((a) => (
                  <button
                    key={a.username}
                    type="button"
                    onClick={() => setUsername(a.username)}
                    aria-pressed={username === a.username}
                    className={`rounded-sm border px-3 py-2 text-left text-sm ${
                      username === a.username ? "border-brand bg-brand-soft" : "border-rule hover:border-ink-3"
                    }`}
                  >
                    <span className="block font-medium">{a.display_name}</span>
                    <span className="text-xs text-ink-3">{ROLE_LABEL[a.role]}</span>
                  </button>
                ))}
              </div>
            </fieldset>
          )}

          <Field label="账号" id="username">
            <input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-sm border border-rule bg-surface px-3 py-2"
              required
            />
          </Field>
          <Field label="密码" id="password">
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-sm border border-rule bg-surface px-3 py-2"
              required
            />
          </Field>
          {config?.access_code_required && (
            <Field label="访问码" id="access-code">
              <input
                id="access-code"
                value={accessCode}
                onChange={(e) => setAccessCode(e.target.value)}
                className="w-full rounded-sm border border-rule bg-surface px-3 py-2"
                required
              />
            </Field>
          )}

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-sm bg-brand px-4 py-2.5 text-sm font-medium text-surface disabled:opacity-40"
          >
            {busy ? "登录中…" : "登录"}
          </button>
          {config?.hint && <p className="text-xs text-ink-3">{config.hint}</p>}
        </form>
        <p className="mt-4 text-xs leading-5 text-ink-3">
          作品集演示系统：机构、产品与客户均为虚构；买入流程只到确认页，不会真实下单。
        </p>
      </div>
    </main>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm">
        {label}
      </label>
      {children}
    </div>
  );
}
