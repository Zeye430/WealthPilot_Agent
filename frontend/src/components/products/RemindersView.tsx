"use client";

import { useCallback, useEffect, useState } from "react";

import { useProductActions } from "@/components/products/ProductActions";
import { Button, Icon } from "@/components/ui";
import { ApiError, cancelReminder, listReminders } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { Reminder } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    title: "我的提醒",
    intro: "新品开售当天会提醒您。提醒不等于购买，开售后需要您本人确认买入。",
    empty: "还没有预约的提醒",
    browse: "看看即将发售的新品",
    meta: (window: string, risk: string, lockup: string) => `募集期 ${window}；${risk}；${lockup}`,
    cancel: "取消提醒",
    loadFailed: "加载失败",
    cancelFailed: "取消失败",
  },
  en: {
    title: "Reminders",
    intro: "We'll remind you on launch day. A reminder isn't a purchase; you confirm it yourself once sales open.",
    empty: "No reminders yet",
    browse: "See what's coming soon",
    meta: (window: string, risk: string, lockup: string) => `${window}, ${risk}, ${lockup}`,
    cancel: "Cancel",
    loadFailed: "Couldn't load reminders",
    cancelFailed: "Couldn't cancel",
  },
});

/** My reminders: sale reminders for upcoming products. A reminder isn't a purchase; at launch the customer confirms the purchase themselves. */
export function RemindersView({ onBrowse }: { onBrowse: () => void }) {
  const c = useCopy(COPY);
  const { open } = useProductActions();
  const [rows, setRows] = useState<Reminder[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listReminders()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : c.loadFailed));
  }, [c.loadFailed]);

  useEffect(load, [load]);

  async function cancel(id: string) {
    try {
      await cancelReminder(id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : c.cancelFailed);
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-5 px-5 pt-2 pb-10 lg:pt-8">
        <h1 className="hidden text-[28px] font-extrabold tracking-tight lg:block">{c.title}</h1>
        <p className="text-sm leading-6 text-ink-2">{c.intro}</p>
        {error && <p className="text-sm text-danger">{error}</p>}
        {rows && rows.length === 0 && (
          <div className="flex flex-col items-center gap-4 rounded-card bg-fill px-5 py-10 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-canvas">
              <Icon name="bell" size={24} />
            </span>
            <p className="font-bold">{c.empty}</p>
            <Button onClick={onBrowse}>{c.browse}</Button>
          </div>
        )}
        <ul className="flex flex-col">
          {rows?.map((r) => (
            <li key={r.id} className="flex items-center gap-3 border-b border-line py-4 last:border-0">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
                <Icon name="bell" size={20} />
              </span>
              <button type="button" onClick={() => open(r.product.code)} className="flex min-w-0 flex-1 flex-col text-left">
                <span className="truncate text-[15px] font-bold">{r.product.name}</span>
                <span className="figures text-[13px] text-ink-3">
                  {c.meta(r.product.sale_window ?? "", r.product.risk_level, r.product.lockup)}
                </span>
                <span className="mt-0.5 text-xs text-ink-3">{r.delivery_note}</span>
              </button>
              <Button variant="quiet" size="sm" onClick={() => cancel(r.id)}>
                {c.cancel}
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
