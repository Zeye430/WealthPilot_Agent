"use client";

import { useState } from "react";

import { useProductActions } from "@/components/products/ProductActions";
import { notifyActed } from "@/components/products/PurchaseFlow";
import { Button, Chip } from "@/components/ui";
import { ApiError, cancelReminder, createReminder, listReminders } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { ProductCard } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    upcoming: "即将发售",
    window: "募集期",
    limit: "募集规模上限",
    limitValue: (l: string) => `${l}，额满提前结束`,
    term: "期限 / 起购",
    termValue: (lockup: string, min: string) => `${lockup}，${min}起`,
    remind: "开售提醒我",
    reminded: "已预约开售提醒",
    cancel: "取消",
    failed: "操作失败，请重试。",
  },
  en: {
    upcoming: "Coming soon",
    window: "Subscription period",
    limit: "Size cap",
    limitValue: (l: string) => `${l}, closes early when full`,
    term: "Term / minimum",
    termValue: (lockup: string, min: string) => `${lockup}, from ${min}`,
    remind: "Remind me at launch",
    reminded: "Reminder set",
    cancel: "Cancel",
    failed: "Something went wrong. Please try again.",
  },
});

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
  const c = useCopy(COPY);
  const { open } = useProductActions();
  return (
    <div className="flex h-full flex-col gap-3 rounded-card bg-fill p-5">
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={() => open(product.code)} className="flex min-w-0 flex-col items-start gap-1.5 text-left">
          <Chip>{c.upcoming}</Chip>
          <span className="text-base leading-snug font-extrabold hover:underline">{product.name}</span>
        </button>
        <span className="figures shrink-0 rounded-full bg-canvas px-2 py-0.5 text-[11px] font-extrabold">{product.risk_level}</span>
      </div>
      <dl className="figures grid grid-cols-2 gap-x-3 gap-y-2.5 text-xs">
        <Item label={c.window}>{product.sale_window}</Item>
        <Item label={c.limit}>{product.raise_limit ? c.limitValue(product.raise_limit) : "—"}</Item>
        <Item label={product.metric.label}>{product.metric.text}</Item>
        <Item label={c.term}>{c.termValue(product.lockup, product.minimum)}</Item>
      </dl>
      <div className="mt-auto pt-1">
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
  const c = useCopy(COPY);
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
        notifyActed();
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : c.failed);
    } finally {
      setBusy(false);
    }
  }

  if (!allowed) {
    return <p className="text-xs leading-5 text-ink-3">{reason}</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {reminded ? (
        <div className="flex h-11 items-center justify-between gap-2 rounded-full bg-brand-soft pr-2 pl-5 text-sm">
          <span className="font-bold text-brand">{c.reminded}</span>
          <button type="button" disabled={busy} onClick={toggle} className="rounded-full px-3 py-1.5 text-xs font-semibold text-ink-2 hover:bg-canvas">
            {c.cancel}
          </button>
        </div>
      ) : (
        <Button variant="secondary" disabled={busy} onClick={toggle} className="w-full">
          {c.remind}
        </Button>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-ink-3">{label}</dt>
      <dd className="mt-0.5 font-semibold">{children}</dd>
    </div>
  );
}
