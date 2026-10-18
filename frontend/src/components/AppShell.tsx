"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AssessmentDialog } from "@/components/AssessmentDialog";
import { Chat, type ChatHandle } from "@/components/Chat";
import { ProductBrowser } from "@/components/products/ProductBrowser";
import {
  listConversations,
  clearNeeds,
  DEMO_USERS,
  formatDate,
  getMe,
  productRiskRange,
  resetDemo,
  setDemoUser as setApiDemoUser,
} from "@/lib/api";
import type { ConversationSummary, CustomerState } from "@/lib/types";

const COMING_SOON = ["我的理财目标"];
const VIEWS = [
  { id: "chat", label: "对话与测算" },
  { id: "products", label: "产品浏览" },
] as const;
type View = (typeof VIEWS)[number]["id"];

export function AppShell() {
  const [demoUser, setDemoUser] = useState(DEMO_USERS[0].id);
  const [chatKey, setChatKey] = useState(0);
  const [state, setState] = useState<CustomerState | null>(null);
  const [assessing, setAssessing] = useState(false);
  const [view, setView] = useState<View>("chat");
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [openConversation, setOpenConversation] = useState<string | null>(null);
  const chatRef = useRef<ChatHandle>(null);

  const refreshState = useCallback(() => {
    getMe()
      .then(setState)
      .catch(() => setState(null));
  }, []);

  const refreshHistory = useCallback(() => {
    listConversations()
      .then(setHistory)
      .catch(() => setHistory([]));
  }, []);

  useEffect(() => {
    setApiDemoUser(demoUser);
    refreshState();
    refreshHistory();
  }, [demoUser, refreshState, refreshHistory]);

  function newChat() {
    setOpenConversation(null);
    setChatKey((k) => k + 1); // 改变 key 会重新挂载 Chat，即开始新对话
    setView("chat");
  }

  function openHistory(id: string) {
    setOpenConversation(id);
    setChatKey((k) => k + 1);
    setView("chat");
  }

  async function reset() {
    await resetDemo();
    refreshState();
    refreshHistory();
    newChat();
  }

  const startAssessment = () => setAssessing(true);

  return (
    <div className="flex h-full">
      <nav className="hidden w-56 shrink-0 flex-col border-r border-rule px-4 py-5 md:flex" aria-label="主导航">
        <Brand />
        <button
          type="button"
          onClick={newChat}
          className="mt-8 rounded-sm border border-brand px-3 py-2 text-left text-sm font-medium text-brand hover:bg-brand-soft"
        >
          新对话
        </button>
        <ul className="mt-6 space-y-1 text-sm">
          {VIEWS.map((v) => (
            <li key={v.id}>
              <button
                type="button"
                onClick={() => setView(v.id)}
                aria-current={view === v.id ? "page" : undefined}
                className={`w-full rounded-sm px-3 py-2 text-left ${
                  view === v.id ? "bg-brand-soft font-medium" : "hover:bg-brand-soft/50"
                }`}
              >
                {v.label}
              </button>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={() => {
                setView("chat");
                chatRef.current?.send("我想联系理财经理");
              }}
              className="w-full rounded-sm px-3 py-2 text-left hover:bg-brand-soft/50"
            >
              联系理财经理
            </button>
          </li>
          {COMING_SOON.map((item) => (
            <li key={item} className="flex items-center justify-between px-3 py-2 text-ink-3">
              {item}
              <span className="text-xs">即将开放</span>
            </li>
          ))}
        </ul>

        {history.length > 0 && (
          <section className="mt-6 min-h-0 overflow-y-auto" aria-label="最近对话">
            <p className="px-3 text-xs text-ink-3">最近对话</p>
            <ul className="mt-1 space-y-0.5 text-sm">
              {history.slice(0, 8).map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => openHistory(c.id)}
                    className={`w-full truncate rounded-sm px-3 py-1.5 text-left ${
                      openConversation === c.id ? "bg-brand-soft" : "text-ink-2 hover:bg-brand-soft/50"
                    }`}
                    title={c.title ?? ""}
                  >
                    {c.title || "未命名对话"}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="mt-auto space-y-2 border-t border-rule pt-4 text-xs text-ink-2">
          <a href="/rm" target="_blank" rel="noreferrer" className="block text-brand underline underline-offset-4">
            打开理财经理看板（演示）
          </a>
          <label htmlFor="demo-user" className="block">
            演示身份
          </label>
          <select
            id="demo-user"
            value={demoUser}
            onChange={(e) => {
              setDemoUser(e.target.value);
              newChat();
            }}
            className="w-full rounded-sm border border-rule bg-surface px-2 py-1.5 text-sm text-ink"
          >
            {DEMO_USERS.map((u) => (
              <option key={u.id} value={u.id}>
                {u.label}
              </option>
            ))}
          </select>
          <button type="button" onClick={reset} className="text-ink-2 underline underline-offset-4 hover:text-ink">
            清空该客户的测评和对话
          </button>
        </section>
      </nav>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-rule px-4 py-3 md:hidden">
          <Brand />
          <div className="flex items-center gap-2">
            <RatingBadge state={state} onStart={startAssessment} />
            <button
              type="button"
              onClick={newChat}
              className="rounded-sm border border-brand px-3 py-1.5 text-sm text-brand"
            >
              新对话
            </button>
          </div>
        </header>
        <nav className="flex border-b border-rule md:hidden" aria-label="页面切换">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setView(v.id)}
              className={`flex-1 py-2 text-sm ${view === v.id ? "border-b-2 border-brand font-medium text-brand" : "text-ink-2"}`}
            >
              {v.label}
            </button>
          ))}
        </nav>
        {view === "products" && (
          <div className="min-h-0 flex-1">
            <ProductBrowser state={state} onStartAssessment={startAssessment} />
          </div>
        )}
        {/* 对话保持挂载，切换到产品页时只隐藏，避免丢失对话内容 */}
        <div className={`min-h-0 flex-1 ${view === "chat" ? "" : "hidden"}`}>
          <Chat
            key={`${demoUser}-${chatKey}`}
            ref={chatRef}
            initialConversationId={openConversation}
            onActivity={refreshHistory}
            onStartAssessment={startAssessment}
            onStateChange={setState}
          />
        </div>
      </main>

      <ContextPanel state={state} onStartAssessment={startAssessment} onStateChange={setState} />

      <AssessmentDialog
        open={assessing}
        onClose={() => setAssessing(false)}
        onConfirmed={(next, result) => {
          setState(next);
          chatRef.current?.addNotice(
            `风险测评已完成：${result.rating} ${result.rating_name}，可购买 ${productRiskRange(result.max_product_risk)} 产品。`,
          );
        }}
      />
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-ink-2">{label}</dt>
      <dd className="figures text-right">{children}</dd>
    </div>
  );
}

function Brand() {
  return (
    <div>
      <p className="font-serif text-lg font-bold leading-tight text-brand">WealthPilot</p>
      <p className="text-xs text-ink-2">理财助手（演示版）</p>
    </div>
  );
}

/** 手机宽度下右栏隐藏，用顶栏的小标签显示测评状态。 */
function RatingBadge({ state, onStart }: { state: CustomerState | null; onStart: () => void }) {
  if (state?.assessment) {
    return (
      <span className="rounded-sm bg-brand-soft px-2 py-1 text-xs font-medium text-brand">
        {state.assessment.rating} {state.assessment.rating_name}
      </span>
    );
  }
  return (
    <button type="button" onClick={onStart} className="rounded-sm bg-notice-soft px-2 py-1 text-xs text-notice">
      未测评
    </button>
  );
}

function ContextPanel({
  state,
  onStartAssessment,
  onStateChange,
}: {
  state: CustomerState | null;
  onStartAssessment: () => void;
  onStateChange: (state: CustomerState) => void;
}) {
  const base = state?.profile.base;
  const needs = state?.profile.needs ?? [];
  const hasNeeds = needs.some((n) => n.value);
  const assessment = state?.assessment;
  const expired = state?.gate_reasons.includes("ASSESSMENT_EXPIRED");

  return (
    <aside className="hidden w-72 shrink-0 flex-col gap-6 overflow-y-auto border-l border-rule px-5 py-5 lg:flex" aria-label="我的情况">
      <section>
        <h2 className="font-serif text-base font-bold">风险测评</h2>
        {assessment ? (
          <div className="mt-2 rounded-sm border border-rule bg-surface px-3 py-3 text-sm">
            <p className="flex items-baseline gap-2">
              <span className="font-serif text-2xl font-bold text-brand">{assessment.rating}</span>
              <span className="font-medium">{assessment.rating_name}</span>
            </p>
            <dl className="mt-2 space-y-1 text-xs text-ink-2">
              <div className="flex justify-between">
                <dt>可购买产品</dt>
                <dd className="figures text-ink">{productRiskRange(assessment.max_product_risk)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>有效期至</dt>
                <dd className="text-ink">{formatDate(assessment.expires_at)}</dd>
              </div>
            </dl>
            <button
              type="button"
              onClick={onStartAssessment}
              className="mt-3 text-xs text-brand underline underline-offset-4"
            >
              重新测评
            </button>
          </div>
        ) : (
          <div className="mt-2 rounded-sm border border-notice/40 bg-notice-soft px-3 py-2.5 text-sm">
            <p className="font-medium text-notice">{expired ? "测评已过期" : "尚未完成"}</p>
            <p className="mt-1 text-xs leading-5 text-ink-2">
              完成风险承受能力测评后，才能为您筛选和比较理财产品。约 3 分钟，共 10 道题。
            </p>
            <button
              type="button"
              onClick={onStartAssessment}
              className="mt-2.5 rounded-sm bg-brand px-3 py-1.5 text-xs font-medium text-surface"
            >
              开始测评
            </button>
          </div>
        )}
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-base font-bold">本次需求</h2>
          {hasNeeds && (
            <button
              type="button"
              onClick={() => clearNeeds().then(onStateChange)}
              className="text-xs text-ink-3 underline underline-offset-4 hover:text-ink"
            >
              清空
            </button>
          )}
        </div>
        <p className="mt-0.5 text-xs text-ink-3">在对话中告诉我，这里会自动记录</p>
        <dl className="mt-2 space-y-2 text-sm">
          {needs.map((n) => (
            <div key={n.field} className="flex items-baseline justify-between gap-3">
              <dt className="shrink-0 text-ink-2">{n.label}</dt>
              <dd className={`figures text-right ${n.value ? "" : "text-ink-3"}`}>
                {n.value ?? "未填写"}
                {n.source && <span className="block text-[11px] text-ink-3">{n.source}</span>}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {base && (
        <section>
          <h2 className="font-serif text-base font-bold">客户资料</h2>
          <p className="mt-0.5 text-xs text-ink-3">{base.source}，只读</p>
          <dl className="mt-2 space-y-1.5 text-sm">
            <Row label="客户">{`${base.display_name}，${base.age} 岁`}</Row>
            <Row label="客户等级">{base.customer_tier}</Row>
            <Row label="活期存款">{base.assets.demand_deposit}</Row>
            <Row label="定期存款">{base.assets.time_deposit}</Row>
            {base.assets.holdings.map((h) => (
              <Row key={h.code} label={h.name}>
                {h.amount}
              </Row>
            ))}
            <Row label="可随时支取">{base.assets.liquid_total}</Row>
            <Row label="专属理财经理">{base.assigned_rm}</Row>
          </dl>
        </section>
      )}

      <p className="mt-auto text-xs leading-5 text-ink-3">
        本系统为作品集演示，使用虚构数据，不销售任何产品，不构成投资建议。
      </p>
    </aside>
  );
}
