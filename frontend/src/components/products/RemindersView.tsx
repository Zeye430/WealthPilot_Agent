"use client";

import { useCallback, useEffect, useState } from "react";

import { useProductActions } from "@/components/products/ProductActions";
import { ApiError, cancelReminder, listReminders } from "@/lib/api";
import type { Reminder } from "@/lib/types";

/** 我的提醒：已预约的新品开售提醒。提醒不等于购买，开售后由客户本人确认买入。 */
export function RemindersView({ onBrowse }: { onBrowse: () => void }) {
  const { open } = useProductActions();
  const [rows, setRows] = useState<Reminder[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listReminders()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : "加载失败"));
  }, []);

  useEffect(load, [load]);

  async function cancel(id: string) {
    try {
      await cancelReminder(id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "取消失败");
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <h1 className="font-serif text-2xl font-bold">我的提醒</h1>
        <p className="mt-2 text-sm text-ink-2">新品开售当天会提醒您。提醒不等于购买，开售后需要您本人确认买入。</p>
        {error && <p className="mt-4 text-sm text-danger">{error}</p>}
        {rows && rows.length === 0 && (
          <div className="mt-6 rounded-sm border border-rule bg-surface px-5 py-6 text-sm">
            <p>还没有预约的提醒。</p>
            <button type="button" onClick={onBrowse} className="mt-3 text-brand underline underline-offset-4">
              看看即将发售的新品
            </button>
          </div>
        )}
        <ul className="mt-6 space-y-3">
          {rows?.map((r) => (
            <li key={r.id} className="rounded-sm border border-rule bg-surface px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={() => open(r.product.code)}
                    className="text-left font-serif text-base font-bold hover:underline"
                  >
                    {r.product.name}
                  </button>
                  <p className="figures mt-1 text-sm text-ink-2">
                    募集期 {r.product.sale_window}，{r.product.risk_level}，{r.product.lockup}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => cancel(r.id)}
                  className="rounded-sm border border-rule px-3 py-1.5 text-sm hover:border-ink-3"
                >
                  取消提醒
                </button>
              </div>
              <p className="mt-2 text-xs text-ink-3">{r.delivery_note}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
