"use client";

import { useState } from "react";

import { Chat } from "@/components/Chat";

const COMING_SOON = ["产品浏览", "我的理财目标", "联系理财经理"];

export function AppShell() {
  const [resetKey, setResetKey] = useState(0);

  return (
    <div className="flex h-full">
      <nav className="hidden w-56 shrink-0 flex-col border-r border-rule px-4 py-5 md:flex" aria-label="主导航">
        <Brand />
        <button
          type="button"
          onClick={() => setResetKey((k) => k + 1)}
          className="mt-8 rounded-sm border border-brand px-3 py-2 text-left text-sm font-medium text-brand hover:bg-brand-soft"
        >
          新对话
        </button>
        <ul className="mt-6 space-y-1 text-sm">
          <li className="rounded-sm bg-brand-soft px-3 py-2 font-medium">财务测算</li>
          {COMING_SOON.map((item) => (
            <li key={item} className="flex items-center justify-between px-3 py-2 text-ink-3">
              {item}
              <span className="text-xs">即将开放</span>
            </li>
          ))}
        </ul>
      </nav>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-rule px-4 py-3 md:hidden">
          <Brand />
          <button
            type="button"
            onClick={() => setResetKey((k) => k + 1)}
            className="rounded-sm border border-brand px-3 py-1.5 text-sm text-brand"
          >
            新对话
          </button>
        </header>
        <div className="min-h-0 flex-1">
          {/* 改变 key 会重新挂载 Chat，即开始新对话 */}
          <Chat key={resetKey} />
        </div>
      </main>

      <ContextPanel />
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

function ContextPanel() {
  const profile = ["投资金额", "投资期限", "目标收益", "流动性储备"];
  return (
    <aside className="hidden w-72 shrink-0 flex-col gap-6 border-l border-rule px-5 py-5 lg:flex" aria-label="我的情况">
      <section>
        <h2 className="font-serif text-base font-bold">风险测评</h2>
        <div className="mt-2 rounded-sm border border-notice/40 bg-notice-soft px-3 py-2.5 text-sm">
          <p className="font-medium text-notice">尚未完成</p>
          <p className="mt-1 text-xs leading-5 text-ink-2">
            完成风险承受能力测评后，才能为您筛选和比较理财产品。测评功能即将开放。
          </p>
        </div>
      </section>

      <section>
        <h2 className="font-serif text-base font-bold">我的情况</h2>
        <dl className="mt-2 space-y-2 text-sm">
          {profile.map((label) => (
            <div key={label} className="flex justify-between">
              <dt className="text-ink-2">{label}</dt>
              <dd className="text-ink-3">未填写</dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="mt-auto text-xs leading-5 text-ink-3">
        本系统为作品集演示，使用虚构数据，不销售任何产品，不构成投资建议。
      </p>
    </aside>
  );
}
