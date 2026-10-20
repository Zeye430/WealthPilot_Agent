"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { Avatar, Button, Chip } from "@/components/ui";
import { ApiError, getSessionUser, logout, opsApi, type OpsOverview, type SessionUser } from "@/lib/api";
import { defineCopy, initial, intlLocale, LocaleToggle, useCopy, useLocale } from "@/lib/i18n";

const POLL_MS = 15000;
const WINDOWS = [1, 24, 168] as const;

const COPY = defineCopy({
  zh: {
    title: "运维看板",
    subtitle: "汇总运行指标；不含对话内容与客户资料，追查问题请用请求编号",
    logout: "退出登录",
    windows: { 1: "近 1 小时", 24: "近 24 小时", 168: "近 7 天" } as Record<number, string>,
    loadFailed: "加载失败",
    updated: (t: string) => `更新于 ${t}，每 15 秒刷新`,
    health: "系统状态",
    ready: "可接收流量",
    notReady: "不可接收流量",
    checks: {
      database: "数据库",
      knowledge_index: "知识库索引",
      llm: "模型服务",
      llm_circuit: "模型熔断",
      speech_model: "语音模型",
    } as Record<string, string>,
    circuit: { CLOSED: "正常", HALF_OPEN: "探测中", OPEN: "已熔断" } as Record<string, string>,
    version: (v: string, sha: string, catalog: string, up: string) => `版本 ${v}（${sha}）· 产品目录 ${catalog} · 已运行 ${up}`,
    kpis: {
      turns: "对话轮次",
      latency: "延迟 P50 / P95",
      fallback: "兜底率",
      error: "异常率",
      rewrite: "审查改写率",
      cost: "模型费用（估算）",
    },
    kpiHints: {
      latency: (max: string) => `最慢 ${max}`,
      fallback: "回答两次未通过审查，改用安全话术",
      error: "模型或系统异常、熔断中",
      rewrite: "首次回答未通过、改写后通过",
      cost: (perTurn: string, tokens: string) => `每轮 ${perTurn} · ${tokens} tokens`,
    },
    latencyChart: "延迟趋势",
    volumeChart: "对话量与需关注的轮次",
    bucket: (b: string) => `每 ${b} 一个点`,
    buckets: { 300: "5 分钟", 3600: "小时", 21600: "6 小时" } as Record<number, string>,
    p50: "P50",
    p95: "P95",
    turnsLabel: "对话",
    problemsLabel: "需关注",
    rules: "合规规则命中",
    rulesEmpty: "所选时间内没有规则命中",
    outcomes: "结果分布",
    intents: "话题分布",
    tools: "工具调用",
    toolCols: ["工具", "成功", "失败"],
    recent: "最近 50 轮",
    cols: ["时间", "请求编号", "语言", "话题", "结果", "审查", "延迟", "模型调用 / tokens"],
    empty: "所选时间内还没有对话",
    copy: "复制请求编号",
    noData: "暂无数据",
    seconds: (s: string) => `${s} 秒`,
  },
  en: {
    title: "Operations dashboard",
    subtitle: "Aggregate runtime metrics; no conversation content or customer data. Trace issues by request ID",
    logout: "Sign out",
    windows: { 1: "Last hour", 24: "Last 24 hours", 168: "Last 7 days" } as Record<number, string>,
    loadFailed: "Couldn't load",
    updated: (t: string) => `Updated ${t}, refreshes every 15 s`,
    health: "System status",
    ready: "Ready for traffic",
    notReady: "Not ready",
    checks: {
      database: "Database",
      knowledge_index: "Knowledge index",
      llm: "Model service",
      llm_circuit: "Model circuit",
      speech_model: "Speech model",
    } as Record<string, string>,
    circuit: { CLOSED: "Normal", HALF_OPEN: "Probing", OPEN: "Open" } as Record<string, string>,
    version: (v: string, sha: string, catalog: string, up: string) => `Version ${v} (${sha}) · catalog ${catalog} · up ${up}`,
    kpis: {
      turns: "Turns",
      latency: "Latency P50 / P95",
      fallback: "Fallback rate",
      error: "Error rate",
      rewrite: "Guard rewrite rate",
      cost: "Model cost (est.)",
    },
    kpiHints: {
      latency: (max: string) => `Slowest ${max}`,
      fallback: "Failed review twice; safe reply used",
      error: "Model or system errors, circuit open",
      rewrite: "First draft failed review, rewrite passed",
      cost: (perTurn: string, tokens: string) => `${perTurn} per turn · ${tokens} tokens`,
    },
    latencyChart: "Latency trend",
    volumeChart: "Turns and turns needing attention",
    bucket: (b: string) => `One point per ${b}`,
    buckets: { 300: "5 minutes", 3600: "hour", 21600: "6 hours" } as Record<number, string>,
    p50: "P50",
    p95: "P95",
    turnsLabel: "Turns",
    problemsLabel: "Needs attention",
    rules: "Compliance rule hits",
    rulesEmpty: "No rule hits in this period",
    outcomes: "Outcomes",
    intents: "Topics",
    tools: "Tool calls",
    toolCols: ["Tool", "OK", "Failed"],
    recent: "Last 50 turns",
    cols: ["Time", "Request ID", "Lang", "Topic", "Outcome", "Review", "Latency", "LLM calls / tokens"],
    empty: "No turns in this period yet",
    copy: "Copy request ID",
    noData: "No data",
    seconds: (s: string) => `${s} s`,
  },
});

const OUTCOME_LABELS: Record<string, { zh: string; en: string; tone: "ok" | "notice" | "danger" | "neutral" }> = {
  ANSWERED: { zh: "已回答", en: "Answered", tone: "ok" },
  OUT_OF_SCOPE: { zh: "超出范围", en: "Out of scope", tone: "neutral" },
  ASSESSMENT_REQUIRED: { zh: "需先测评", en: "Needs profile", tone: "neutral" },
  FALLBACK: { zh: "兜底", en: "Fallback", tone: "notice" },
  TOOL_LIMIT: { zh: "工具上限", en: "Tool limit", tone: "notice" },
  TIMEOUT: { zh: "超时", en: "Timeout", tone: "notice" },
  ERROR: { zh: "异常", en: "Error", tone: "danger" },
  BREAKER_OPEN: { zh: "熔断", en: "Circuit open", tone: "danger" },
};

const INTENT_LABELS: Record<string, { zh: string; en: string }> = {
  FINANCE_KNOWLEDGE: { zh: "金融常识", en: "Knowledge" },
  CALCULATION: { zh: "测算", en: "Calculation" },
  PRODUCT_OR_ADVICE: { zh: "产品与建议", en: "Products" },
  HANDOFF: { zh: "转人工", en: "Handoff" },
  SERVICE: { zh: "服务类", en: "Service" },
  OUT_OF_SCOPE: { zh: "无关话题", en: "Off-topic" },
};

const RULE_LABELS: Record<string, { zh: string; en: string }> = {
  "O-PROHIBITED_CLAIM": { zh: "承诺收益 / 保本", en: "Guarantee claims" },
  "O-PERMISSION_LEAK": { zh: "测评前泄露产品", en: "Product leak before profile" },
  "O-UNGROUNDED_PRODUCT": { zh: "产品无来源", en: "Ungrounded product" },
  "O-UNSUITABLE_RECOMMENDATION": { zh: "推荐超评级产品", en: "Unsuitable recommendation" },
  "O-PRESSURE_SALES": { zh: "制造紧迫感", en: "Pressure sales" },
  "O-RETURN_PITCH": { zh: "以收益为推荐理由", en: "Return-based pitch" },
  "O-GIFT_FOR_PURCHASE": { zh: "买产品送礼", en: "Gift for purchase" },
  "O-METRIC_MIXING": { zh: "跨口径比较收益", en: "Metric mixing" },
  "O-UNGROUNDED_FIGURE": { zh: "收益数字无来源", en: "Ungrounded yield figure" },
  "O-UNGROUNDED_AMOUNT": { zh: "金额无来源（模型自算）", en: "Ungrounded amount" },
  "O-REASSESSMENT_STEERING": { zh: "诱导重新测评", en: "Re-profiling steer" },
  "O-FALSE_HANDOFF_CLAIM": { zh: "虚假人工接入", en: "False handoff claim" },
  "O-FALSE_ACTION_CLAIM": { zh: "宣称未完成的操作", en: "False action claim" },
  "O-REAL_INSTITUTION": { zh: "提及真实机构", en: "Real institution" },
  "O-FAKE_CITATION": { zh: "编造出处", en: "Fake citation" },
};

function pct(v: number) {
  return `${(v * 100).toFixed(v > 0 && v < 0.01 ? 2 : 1)}%`;
}

function secs(ms: number) {
  return (ms / 1000).toFixed(1);
}

function uptime(seconds: number, locale: "zh" | "en") {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return locale === "en" ? `${h}h ${m}m` : `${h} 小时 ${m} 分`;
}

/**
 * Ops dashboard (demo): read-only aggregate metrics from turn_metrics (one row per turn) and the readiness check,
 * with no conversation content or customer data; to investigate, use the request ID to search logs and the access-controlled audit tables.
 */
export function OpsDashboard() {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const router = useRouter();
  const [me, setMe] = useState<SessionUser | null>(null);
  const [hours, setHours] = useState<number>(24);
  const [data, setData] = useState<OpsOverview | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSessionUser()
      .then((u) => (u.role === "ops" ? setMe(u) : router.replace(u.role === "rm" ? "/rm" : "/")))
      .catch(() => router.replace("/login?next=/ops"));
  }, [router]);

  const refresh = useCallback(async () => {
    if (!me) return;
    try {
      setData(await opsApi.overview(hours));
      setUpdatedAt(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : c.loadFailed);
    }
  }, [me, hours, c.loadFailed]);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh]);

  const k = data?.kpis;
  const fmtTime = (iso: string, withDate = false) =>
    new Date(iso).toLocaleString(intlLocale(locale), {
      ...(withDate ? { month: "numeric", day: "numeric" } : {}),
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-canvas">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-4 lg:px-8">
        <div className="min-w-0">
          <h1 className="text-xl font-extrabold tracking-tight">{c.title}</h1>
          <p className="text-xs text-ink-3">{c.subtitle}</p>
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

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="radiogroup" aria-label={c.windows[hours]} className="flex gap-1.5 rounded-full bg-fill p-1">
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                role="radio"
                aria-checked={hours === w}
                onClick={() => setHours(w)}
                className={`h-9 rounded-full px-4 text-sm font-bold transition-colors ${
                  hours === w ? "bg-navy text-white" : "text-ink-2 hover:text-ink"
                }`}
              >
                {c.windows[w]}
              </button>
            ))}
          </div>
          {updatedAt && <p className="text-xs text-ink-3">{c.updated(updatedAt.toLocaleTimeString(intlLocale(locale)))}</p>}
        </div>

        {error && <p className="rounded-2xl bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</p>}

        {data && (
          <>
            <HealthStrip data={data} />

            <section className="grid grid-cols-2 gap-3 lg:grid-cols-6" aria-label="KPI">
              <Kpi label={c.kpis.turns} value={k!.turns.toLocaleString(intlLocale(locale))} />
              <Kpi
                label={c.kpis.latency}
                value={`${secs(k!.p50_ms)} / ${secs(k!.p95_ms)}`}
                unit={locale === "en" ? "s" : "秒"}
                hint={c.kpiHints.latency(c.seconds(secs(k!.max_ms)))}
              />
              <Kpi label={c.kpis.fallback} value={pct(k!.fallback_rate)} hint={c.kpiHints.fallback} warn={k!.fallback_rate > 0.05} />
              <Kpi label={c.kpis.error} value={pct(k!.error_rate)} hint={c.kpiHints.error} warn={k!.error_rate > 0.02} />
              <Kpi label={c.kpis.rewrite} value={pct(k!.rewrite_rate)} hint={c.kpiHints.rewrite} />
              <Kpi
                label={c.kpis.cost}
                value={`$${k!.cost_usd.toFixed(k!.cost_usd < 1 ? 4 : 2)}`}
                hint={c.kpiHints.cost(`$${k!.cost_per_turn_usd.toFixed(4)}`, (k!.prompt_tokens + k!.completion_tokens).toLocaleString(intlLocale(locale)))}
              />
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <LatencyChart data={data} fmtHour={(h) => fmtTime(h, hours > 24)} note={c.bucket(c.buckets[data.bucket_seconds])} />
              <VolumeChart data={data} fmtHour={(h) => fmtTime(h, hours > 24)} note={c.bucket(c.buckets[data.bucket_seconds])} />
            </section>

            <section className="grid gap-4 lg:grid-cols-3">
              <Panel title={c.rules}>
                <Bars
                  rows={Object.entries(data.guard.rules).map(([code, n]) => ({
                    key: code,
                    label: RULE_LABELS[code]?.[locale] ?? code,
                    sub: code,
                    value: n,
                  }))}
                  empty={c.rulesEmpty}
                />
              </Panel>
              <Panel title={c.outcomes}>
                <Bars
                  rows={Object.entries(data.outcomes)
                    .sort((a, b) => b[1] - a[1])
                    .map(([o, n]) => ({ key: o, label: OUTCOME_LABELS[o]?.[locale] ?? o, value: n }))}
                  empty={c.noData}
                />
              </Panel>
              <Panel title={c.intents}>
                <Bars
                  rows={Object.entries(data.intents)
                    .sort((a, b) => b[1] - a[1])
                    .map(([i, n]) => ({ key: i, label: INTENT_LABELS[i]?.[locale] ?? i, value: n }))}
                  empty={c.noData}
                />
              </Panel>
            </section>

            <Panel title={c.tools}>
              {Object.keys(data.tools).length === 0 ? (
                <p className="text-sm text-ink-3">{c.noData}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="figures w-full min-w-[22rem] text-sm">
                    <thead className="text-left text-xs text-ink-3">
                      <tr>
                        {c.toolCols.map((h, i) => (
                          <th key={h} className={`py-1.5 font-semibold ${i ? "text-right" : ""}`}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.tools).map(([name, s]) => (
                        <tr key={name} className="border-t border-line">
                          <td className="py-1.5 font-mono text-xs">{name}</td>
                          <td className="py-1.5 text-right">{s.success ?? 0}</td>
                          <td className={`py-1.5 text-right ${s.error ? "font-bold text-danger" : "text-ink-3"}`}>{s.error ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <Panel title={c.recent}>
              {data.recent.length === 0 ? (
                <p className="text-sm text-ink-3">{c.empty}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="figures w-full min-w-[56rem] text-sm">
                    <thead className="text-left text-xs text-ink-3">
                      <tr>
                        {c.cols.map((h) => (
                          <th key={h} className="py-1.5 pr-3 font-semibold">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent.map((r) => {
                        const o = OUTCOME_LABELS[r.outcome];
                        return (
                          <tr key={r.request_id + r.at} className="border-t border-line align-top">
                            <td className="py-2 pr-3 whitespace-nowrap">{fmtTime(r.at, true)}</td>
                            <td className="py-2 pr-3">
                              <button
                                type="button"
                                title={c.copy}
                                onClick={() => navigator.clipboard?.writeText(r.request_id)}
                                className="font-mono text-xs text-brand hover:underline"
                              >
                                {r.request_id.slice(0, 12)}
                              </button>
                            </td>
                            <td className="py-2 pr-3 uppercase">{r.locale}</td>
                            <td className="py-2 pr-3">{r.intent ? INTENT_LABELS[r.intent]?.[locale] ?? r.intent : "—"}</td>
                            <td className="py-2 pr-3">
                              <Chip tone={o?.tone ?? "neutral"}>{o?.[locale] ?? r.outcome}</Chip>
                            </td>
                            <td className="py-2 pr-3 text-xs">
                              {r.guard_decision ?? "—"}
                              {r.violation_codes.length > 0 && (
                                <span className="mt-0.5 block text-ink-3">{r.violation_codes.join(", ")}</span>
                              )}
                            </td>
                            <td className="py-2 pr-3 whitespace-nowrap">{c.seconds(secs(r.latency_ms))}</td>
                            <td className="py-2 pr-3 whitespace-nowrap">
                              {r.llm_calls} / {r.tokens.toLocaleString(intlLocale(locale))}
                              {r.tool_errors > 0 && <span className="ml-2 font-bold text-danger">⚠ {r.tool_errors}</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </>
        )}
      </main>
    </div>
  );
}

function HealthStrip({ data }: { data: OpsOverview }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const h = data.health;
  return (
    <section className="flex flex-col gap-3 rounded-card bg-fill p-5" aria-label={c.health}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[15px] font-extrabold">{c.health}</span>
        <Chip tone={h.status === "ready" ? "ok" : "danger"}>{h.status === "ready" ? `✓ ${c.ready}` : `✕ ${c.notReady}`}</Chip>
        {Object.entries(h.checks).map(([name, check]) => {
          const detail = name === "llm_circuit" ? c.circuit[String(check.state)] : name === "llm" ? String(check.model ?? "") : name === "knowledge_index" && check.chunks != null ? String(check.chunks) : "";
          const tone = check.ok ? "neutral" : check.required ? "danger" : "notice";
          return (
            <Chip key={name} tone={tone}>
              <span aria-hidden className="mr-1">
                {check.ok ? "●" : "▲"}
              </span>
              {c.checks[name] ?? name}
              {detail && <span className="ml-1 font-semibold opacity-70">{detail}</span>}
            </Chip>
          );
        })}
      </div>
      <p className="text-xs text-ink-3">{c.version(h.version, h.git_sha, h.catalog_version, uptime(h.uptime_seconds, locale))}</p>
    </section>
  );
}

function Kpi({ label, value, unit, hint, warn = false }: { label: string; value: string; unit?: string; hint?: string; warn?: boolean }) {
  return (
    <div className={`flex flex-col gap-1 rounded-card p-4 ${warn ? "bg-notice-soft" : "bg-fill"}`}>
      <span className="text-xs font-semibold text-ink-2">{label}</span>
      <span className="figures text-[26px] leading-tight font-extrabold tracking-tight">
        {value}
        {unit && <span className="ml-1 text-sm font-bold text-ink-2">{unit}</span>}
      </span>
      {hint && <span className="text-[11px] leading-4 text-ink-3">{hint}</span>}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-card bg-fill p-5">
      <h2 className="mb-3 text-[15px] font-extrabold">{title}</h2>
      {children}
    </section>
  );
}

/** Bar list for a single quantity: one color, sorted by value descending, with values written out. */
function Bars({ rows, empty }: { rows: { key: string; label: string; sub?: string; value: number }[]; empty: string }) {
  if (rows.length === 0) return <p className="text-sm text-ink-3">{empty}</p>;
  const max = Math.max(...rows.map((r) => r.value));
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((r) => (
        <li key={r.key} title={r.sub}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">{r.label}</span>
            <span className="figures font-bold">{r.value}</span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-line">
            <div className="h-2 rounded-full bg-[var(--series-1)]" style={{ width: `${(r.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function ChartFrame({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <figure className="rounded-card bg-fill px-3 pt-5 pb-3 sm:px-5">
      <figcaption className="flex items-baseline justify-between gap-3 px-2">
        <span className="text-[15px] font-extrabold">{title}</span>
        {note && <span className="text-xs text-ink-3">{note}</span>}
      </figcaption>
      <div className="mt-3 h-60 w-full">{children}</div>
    </figure>
  );
}

function LatencyChart({ data, fmtHour, note }: { data: OpsOverview; fmtHour: (h: string) => string; note: string }) {
  const c = useCopy(COPY);
  const rows = data.series.map((s) => ({
    hour: s.start,
    [c.p50]: s.p50_ms == null ? null : s.p50_ms / 1000,
    [c.p95]: s.p95_ms == null ? null : s.p95_ms / 1000,
  }));
  if (data.kpis.turns === 0) {
    return (
      <ChartFrame title={c.latencyChart} note={note}>
        <p className="px-2 text-sm text-ink-3">{c.noData}</p>
      </ChartFrame>
    );
  }
  return (
    <ChartFrame title={c.latencyChart} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="hour" tickFormatter={fmtHour} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={{ stroke: "var(--line)" }} tickLine={false} minTickGap={24} />
          <YAxis tickFormatter={(v) => `${v}s`} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
          <Tooltip content={(p) => <SeriesTooltip {...p} fmtHour={fmtHour} unit="s" />} cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }} />
          <Legend verticalAlign="top" align="left" iconType="plainline" wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>} />
          {[c.p50, c.p95].map((name, i) => (
            <Line key={name} dataKey={name} stroke={`var(--series-${i + 1})`} strokeWidth={2} dot={{ r: 2.5, strokeWidth: 0, fill: `var(--series-${i + 1})` }} activeDot={{ r: 4, stroke: "var(--fill)", strokeWidth: 2 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

function VolumeChart({ data, fmtHour, note }: { data: OpsOverview; fmtHour: (h: string) => string; note: string }) {
  const c = useCopy(COPY);
  const rows = data.series.map((s) => ({ hour: s.start, [c.turnsLabel]: s.turns, [c.problemsLabel]: s.problems }));
  if (data.kpis.turns === 0) {
    return (
      <ChartFrame title={c.volumeChart} note={note}>
        <p className="px-2 text-sm text-ink-3">{c.noData}</p>
      </ChartFrame>
    );
  }
  return (
    <ChartFrame title={c.volumeChart} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="hour" tickFormatter={fmtHour} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={{ stroke: "var(--line)" }} tickLine={false} minTickGap={24} />
          <YAxis allowDecimals={false} tick={{ fill: "var(--ink-3)", fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
          <Tooltip content={(p) => <SeriesTooltip {...p} fmtHour={fmtHour} />} cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }} />
          <Legend verticalAlign="top" align="left" iconType="plainline" wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>} />
          <Line dataKey={c.turnsLabel} stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey={c.problemsLabel} stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

function SeriesTooltip({ active, payload, label, fmtHour, unit = "" }: TooltipContentProps & { fmtHour: (h: string) => string; unit?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="figures rounded-2xl bg-surface px-3 py-2 text-xs shadow-[0_4px_20px_rgba(10,31,61,0.12)]">
      <p className="mb-1 text-ink-2">{fmtHour(String(label))}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-ink">
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
          <span className="text-ink-2">{p.name}</span>
          <span className="ml-auto pl-3 font-bold">
            {p.value == null ? "—" : `${Number(p.value).toFixed(unit ? 1 : 0)}${unit}`}
          </span>
        </p>
      ))}
    </div>
  );
}
