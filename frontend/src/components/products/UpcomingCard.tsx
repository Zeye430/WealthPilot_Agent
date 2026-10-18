"use client";

import { useState } from "react";

import { useProductActions } from "@/components/products/ProductActions";
import { ApiError, cancelReminder, createReminder, listReminders } from "@/lib/api";
import type { ProductCard } from "@/lib/types";

/**
 * 即将发售的新品卡片：如实展示募集期、募集规模上限和业绩比较基准，客户自己决定是否预约提醒。
 * 不用「抢购」「限量」等字眼，额度只作为事实说明。
 */
export function UpcomingCard({
  product,
  reminded,
  remindAllowed = true,
  reason,
}: {
  product: ProductCard;
  reminded: boolean;
  remindAllowed?: boolean;
  reason?: string | null;
}) {
  const { open } = useProductActions();
  return (
    <div className="flex h-full flex-col rounded-sm border border-rule bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={() => open(product.code)} className="min-w-0 text-left">
          <p className="text-xs font-medium text-brand">即将发售</p>
          <p className="mt-0.5 font-serif text-base font-bold leading-snug hover:underline">{product.name}</p>
        </button>
        <span className="figures shrink-0 rounded-sm border border-ink-3 px-1.5 py-0.5 text-xs font-medium">
          {product.risk_level}
        </span>
      </div>
      <dl className="figures mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        <Item label="募集期">{product.sale_window}</Item>
        <Item label="募集规模上限">{product.raise_limit ? `${product.raise_limit}，额满提前结束` : "—"}</Item>
        <Item label={product.metric.label}>{product.metric.text}</Item>
        <Item label="期限 / 起购">{`${product.lockup}，${product.minimum}起`}</Item>
      </dl>
      <div className="mt-auto pt-3">
        <RemindButton code={product.code} initial={reminded} allowed={remindAllowed} reason={reason} />
      </div>
    </div>
  );
}

/** 「开售提醒我」：客户本人点击才预约；已预约时可取消。规则由后端校验（评级、是否新品）。 */
export function RemindButton({
  code,
  initial,
  allowed = true,
  reason,
}: {
  code: string;
  initial: boolean;
  allowed?: boolean;
  reason?: string | null;
}) {
  const [reminded, setReminded] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      if (reminded) {
        const existing = (await listReminders()).find((r) => r.product.code === code);
        if (existing) await cancelReminder(existing.id);
        setReminded(false);
      } else {
        await createReminder(code);
        setReminded(true);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "操作失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  if (!allowed) {
    return <p className="text-xs leading-5 text-ink-3">{reason}</p>;
  }
  return (
    <div>
      {reminded ? (
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="font-medium text-brand">已预约开售提醒</span>
          <button type="button" disabled={busy} onClick={toggle} className="text-xs text-ink-3 underline underline-offset-4">
            取消
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={toggle}
          className="w-full rounded-sm border border-brand px-3 py-2 text-sm font-medium text-brand hover:bg-brand-soft disabled:opacity-40"
        >
          开售提醒我
        </button>
      )}
      {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
    </div>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-ink-3">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
