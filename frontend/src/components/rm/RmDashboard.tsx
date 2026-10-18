"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, DEMO_RMS, rmApi, type RmHandoffDetail, type RmHandoffRow } from "@/lib/api";

const POLL_MS = 3000;

/**
 * 理财经理看板（演示）：查看客户联系前同步过来的咨询要点。
 * 客户通过名片上的企业微信 / 电话联系理财经理，看板只用于了解情况和标记跟进状态。
 */
export function RmDashboard() {
  const [rm, setRm] = useState(DEMO_RMS[0].id);
  const [rows, setRows] = useState<RmHandoffRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RmHandoffDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRows(await rmApi.list(rm));
      if (selected) setDetail(await rmApi.detail(rm, selected));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败");
    }
  }, [rm, selected]);

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
      setError(e instanceof ApiError ? e.message : "操作失败");
    }
  }

  const canResolve = detail && (detail.status === "PENDING" || detail.status === "ACCEPTED");

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-5 py-3">
        <div>
          <p className="font-serif text-lg font-bold text-brand">理财经理看板</p>
          <p className="text-xs text-ink-2">演示系统：理财经理与客户均为虚构</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-ink-2">当前身份</span>
          <select
            value={rm}
            onChange={(e) => {
              setRm(e.target.value);
              setSelected(null);
              setDetail(null);
            }}
            className="rounded-sm border border-rule bg-surface px-2 py-1.5"
          >
            {DEMO_RMS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <aside className="border-b border-rule md:w-80 md:border-r md:border-b-0" aria-label="交接请求">
          <p className="px-5 pt-4 text-xs font-medium text-ink-2">客户咨询</p>
          {rows.length === 0 && <p className="px-5 py-3 text-sm text-ink-3">暂无咨询</p>}
          <ul className="space-y-1 p-3">
            {rows.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelected(r.id);
                    rmApi.detail(rm, r.id).then(setDetail);
                  }}
                  className={`w-full rounded-sm border px-3 py-2.5 text-left text-sm ${
                    selected === r.id ? "border-brand bg-brand-soft" : "border-rule hover:border-ink-3"
                  }`}
                >
                  <span className="flex justify-between gap-2">
                    <span className="font-medium">{r.customer_name}</span>
                    <span className="text-xs text-ink-2">{r.status_label}</span>
                  </span>
                  <span className="mt-0.5 block text-xs text-ink-3">{r.reason}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {error && <p className="mb-3 text-sm text-danger">{error}</p>}
          {!detail ? (
            <p className="text-sm text-ink-3">选择左侧的客户咨询查看要点。</p>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h1 className="font-serif text-xl font-bold">{detail.summary.customer?.display_name ?? "客户"}</h1>
                  <p className="text-sm text-ink-2">
                    {detail.status_label}，原因：{detail.summary.reason}
                  </p>
                </div>
                <div className="flex gap-2">
                  {detail.status === "PENDING" && (
                    <button
                      type="button"
                      onClick={() => act(() => rmApi.accept(rm, detail.id))}
                      className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface"
                    >
                      标记跟进中
                    </button>
                  )}
                  {canResolve && (
                    <button
                      type="button"
                      onClick={() => act(() => rmApi.resolve(rm, detail.id))}
                      className="rounded-sm border border-rule px-4 py-2 text-sm hover:border-ink-3"
                    >
                      结束跟进
                    </button>
                  )}
                </div>
              </div>

              <section className="rounded-sm border border-rule bg-surface px-4 py-3 text-sm">
                <h2 className="font-serif font-bold">咨询要点</h2>
                <p className="mt-0.5 text-xs text-ink-3">由系统根据客户资料与对话自动生成，包括：{detail.sync_scope.join("、")}</p>
                <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
                  {detail.summary.customer && (
                    <Item label="客户资料">
                      {detail.summary.customer.age} 岁，{detail.summary.customer.customer_tier}；可随时支取约{" "}
                      {detail.summary.customer.assets.liquid_total}
                    </Item>
                  )}
                  <Item label="风险测评">{detail.summary.assessment}</Item>
                  <Item label="本次需求">
                    {detail.summary.needs.map((n) => `${n.label} ${n.value}`).join("；") || "未提供"}
                  </Item>
                  <Item label="已了解的产品">{detail.summary.products_discussed.join("、") || "无"}</Item>
                  <Item label="待跟进问题">{detail.summary.open_questions.join("；") || "无"}</Item>
                </dl>
              </section>

              <section>
                <h2 className="font-serif font-bold">对话记录</h2>
                <ol className="mt-2 space-y-2 text-sm">
                  {detail.messages.map((m, i) => (
                    <li key={i} className={m.role === "user" ? "text-right" : ""}>
                      <span className="block text-[11px] text-ink-3">
                        {{ user: "客户", assistant: "AI 助手", rm: "理财经理（旧版应用内回复）" }[m.role]}
                      </span>
                      <span
                        className={`inline-block max-w-[85%] rounded-sm px-3 py-2 text-left leading-6 whitespace-pre-wrap ${
                          m.role === "user" ? "bg-brand-soft" : m.role === "rm" ? "border-l-2 border-brand bg-surface" : "bg-paper"
                        }`}
                      >
                        {m.content || "（已转给理财经理）"}
                      </span>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="text-xs text-ink-3">
                <h2 className="font-medium text-ink-2">状态记录</h2>
                <ul className="mt-1 space-y-0.5">
                  {detail.events.map((e, i) => (
                    <li key={i}>
                      {new Date(e.at).toLocaleString("zh-CN")}：{e.to}（{e.actor}）
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
      <dd className="mt-0.5 leading-6">{children}</dd>
    </div>
  );
}
