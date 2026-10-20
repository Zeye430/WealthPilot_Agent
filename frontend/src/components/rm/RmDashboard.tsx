"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Avatar, Button, Chip } from "@/components/ui";
import {
  ApiError,
  getSessionUser,
  logout,
  rmApi,
  type RmHandoffDetail,
  type RmHandoffRow,
  type SessionUser,
} from "@/lib/api";
import { defineCopy, intlLocale, LocaleToggle, useCopy, useLocale, useSeparators, initial } from "@/lib/i18n";

const POLL_MS = 3000;

const COPY = defineCopy({
  zh: {
    title: "理财经理看板",
    demo: "演示系统：理财经理与客户均为虚构",
    logout: "退出登录",
    inbox: "客户咨询",
    empty: "暂无咨询",
    pick: "选择左侧的客户咨询查看要点。",
    reason: (status: string, reason: string) => `${status}；原因：${reason}`,
    accept: "标记跟进中",
    resolve: "结束跟进",
    summary: "咨询要点",
    generated: (scope: string) => `由系统根据客户资料与对话自动生成，包括：${scope}`,
    profile: "客户资料",
    profileValue: (age: number, tier: string, liquid: string) => `${age} 岁，${tier}；可随时支取约 ${liquid}`,
    assessment: "风险测评",
    needs: "本次需求",
    none: "未提供",
    products: "已了解的产品",
    noProducts: "无",
    questions: "待跟进问题",
    transcript: "对话记录",
    roles: { user: "客户", assistant: "AI 助手", rm: "理财经理（旧版应用内回复）" } as Record<string, string>,
    events: "状态记录",
    loadFailed: "加载失败",
    failed: "操作失败",
    customer: "客户",
    event: (at: string, to: string, actor: string) => `${at}：${to}（${actor}）`,
  },
  en: {
    title: "RM dashboard",
    demo: "Demo: relationship managers and customers are fictional",
    logout: "Sign out",
    inbox: "Customer requests",
    empty: "No requests",
    pick: "Select a request to see the summary.",
    reason: (status: string, reason: string) => `${status}. Reason: ${reason}`,
    accept: "Mark as following up",
    resolve: "Close",
    summary: "Summary",
    generated: (scope: string) => `Generated from bank records and the conversation: ${scope}`,
    profile: "Profile",
    profileValue: (age: number, tier: string, liquid: string) => `${age}, ${tier}; about ${liquid} available anytime`,
    assessment: "Risk profile",
    needs: "Goals",
    none: "Not provided",
    products: "Products discussed",
    noProducts: "None",
    questions: "Open questions",
    transcript: "Transcript",
    roles: { user: "Customer", assistant: "AI assistant", rm: "RM (legacy in-app reply)" } as Record<string, string>,
    events: "Status history",
    loadFailed: "Couldn't load",
    failed: "Something went wrong",
    customer: "Customer",
    event: (at: string, to: string, actor: string) => `${at}: ${to} (${actor})`,
  },
});

/**
 * Relationship manager dashboard (demo): view the summary shared before the customer gets in touch.
 * Customers contact the RM via WeCom or phone on the contact card; the dashboard is only for context and marking follow-up status.
 */
export function RmDashboard() {
  const c = useCopy(COPY);
  const sep = useSeparators();
  const { locale } = useLocale();
  const router = useRouter();
  const [me, setMe] = useState<SessionUser | null>(null);
  const [rows, setRows] = useState<RmHandoffRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RmHandoffDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Only RM accounts may enter; customer accounts go back to the customer home, signed-out users to the sign-in page
    getSessionUser()
      .then((u) => (u.role === "rm" ? setMe(u) : router.replace("/")))
      .catch(() => router.replace("/login?next=/rm"));
  }, [router]);

  const refresh = useCallback(async () => {
    if (!me) return;
    try {
      setRows(await rmApi.list());
      if (selected) setDetail(await rmApi.detail(selected));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : c.loadFailed);
    }
  }, [me, selected, c.loadFailed]);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : c.failed);
    }
  }

  const canResolve = detail && (detail.status === "PENDING" || detail.status === "ACCEPTED");

  return (
    <div className="flex h-full flex-col bg-canvas">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 lg:px-8">
        <div>
          <p className="text-xl font-extrabold tracking-tight">{c.title}</p>
          <p className="text-xs text-ink-3">{c.demo}</p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {me && (
            <span className="flex items-center gap-2 font-semibold">
              <Avatar text={initial(me.display_name)} tone="navy" />
              <span className="hidden sm:inline">{me.display_name}</span>
            </span>
          )}
          <LocaleToggle />
          <Button variant="quiet" size="sm" onClick={() => logout().finally(() => router.replace("/login"))}>
            {c.logout}
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <aside className="border-b border-line bg-fill md:w-80 md:shrink-0 md:border-b-0" aria-label={c.inbox}>
          <p className="px-5 pt-5 text-xs font-bold text-ink-3">{c.inbox}</p>
          {rows.length === 0 && <p className="px-5 py-3 text-sm text-ink-3">{c.empty}</p>}
          <ul className="flex flex-col gap-1.5 p-3">
            {rows.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelected(r.id);
                    rmApi.detail(r.id).then(setDetail);
                  }}
                  className={`flex w-full flex-col gap-1 rounded-2xl px-4 py-3 text-left text-sm ${
                    selected === r.id ? "bg-canvas ring-2 ring-brand" : "hover:bg-canvas"
                  }`}
                >
                  {/* Status chip on its own line: English labels are long and would overflow the sidebar next to the customer name */}
                  <span className="flex flex-col items-start gap-1.5">
                    <span className="font-bold">{r.customer_name}</span>
                    <Chip tone={r.status === "PENDING" ? "notice" : r.status === "ACCEPTED" ? "brand" : "neutral"}>{r.status_label}</Chip>
                  </span>
                  <span className="text-xs text-ink-3">{r.reason}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="min-h-0 flex-1 overflow-y-auto px-5 py-6 lg:px-8">
          {error && <p className="mb-3 text-sm text-danger">{error}</p>}
          {!detail ? (
            <p className="text-sm text-ink-3">{c.pick}</p>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h1 className="text-2xl font-extrabold tracking-tight">{detail.summary.customer?.display_name ?? c.customer}</h1>
                  <p className="text-sm text-ink-2">{c.reason(detail.status_label, detail.summary.reason)}</p>
                </div>
                <div className="flex gap-2">
                  {detail.status === "PENDING" && <Button onClick={() => act(() => rmApi.accept(detail.id))}>{c.accept}</Button>}
                  {canResolve && (
                    <Button variant="secondary" onClick={() => act(() => rmApi.resolve(detail.id))}>
                      {c.resolve}
                    </Button>
                  )}
                </div>
              </div>

              <section className="rounded-card bg-fill p-5 text-sm">
                <h2 className="text-[17px] font-extrabold">{c.summary}</h2>
                <p className="mt-0.5 text-xs text-ink-3">{c.generated(detail.sync_scope.join(sep.comma))}</p>
                <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  {detail.summary.customer && (
                    <Item label={c.profile}>
                      {c.profileValue(detail.summary.customer.age, detail.summary.customer.customer_tier, detail.summary.customer.assets.liquid_total)}
                    </Item>
                  )}
                  <Item label={c.assessment}>{detail.summary.assessment}</Item>
                  <Item label={c.needs}>{detail.summary.needs.map((n) => `${n.label} ${n.value}`).join(sep.semi) || c.none}</Item>
                  <Item label={c.products}>{detail.summary.products_discussed.join(sep.comma) || c.noProducts}</Item>
                  <Item label={c.questions}>{detail.summary.open_questions.join(sep.semi) || c.noProducts}</Item>
                </dl>
              </section>

              <section>
                <h2 className="text-[17px] font-extrabold">{c.transcript}</h2>
                <ol className="mt-3 flex flex-col gap-3 text-sm">
                  {detail.messages.map((m, i) => (
                    <li key={i} className={m.role === "user" ? "flex flex-col items-end" : "flex flex-col items-start"}>
                      <span className="text-[11px] text-ink-3">{c.roles[m.role]}</span>
                      <span
                        className={`mt-0.5 max-w-[85%] rounded-[18px] px-4 py-2.5 leading-6 whitespace-pre-wrap ${
                          m.role === "user" ? "rounded-br-md bg-brand text-on-brand" : "rounded-bl-md bg-fill"
                        }`}
                      >
                        {m.content}
                      </span>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="text-xs text-ink-3">
                <h2 className="font-bold text-ink-2">{c.events}</h2>
                <ul className="mt-1 flex flex-col gap-0.5">
                  {detail.events.map((e, i) => (
                    <li key={i} className="figures">
                      {c.event(new Date(e.at).toLocaleString(intlLocale(locale)), e.to, e.actor)}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-0.5 leading-6 font-semibold">{children}</dd>
    </div>
  );
}
