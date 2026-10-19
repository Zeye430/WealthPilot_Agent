"use client";

import { clearNeeds, formatDate, formatMoney } from "@/lib/api";
import { defineCopy, useCopy, useLocale } from "@/lib/i18n";
import type { CustomerState } from "@/lib/types";

import { Avatar, Button, ChevronRight } from "./ui";

/** 评级的英文名（后端返回中文名，英文界面按代码映射） */
export const RATING_EN: Record<string, string> = {
  C1: "Conservative",
  C2: "Steady",
  C3: "Balanced",
  C4: "Growth",
  C5: "Aggressive",
};

const COPY = defineCopy({
  zh: {
    assets: "在本行金融资产",
    liquid: "可随时支取",
    wealth: "理财持仓",
    toNext: (name: string, gap: string) => `距${name}还差 ${gap}`,
    risk: "风险测评",
    canBuy: (range: string) => `可购买 ${range}`,
    validUntil: (d: string) => `有效期至 ${d}`,
    retake: "重新测评",
    notAssessed: "尚未完成风险测评",
    expired: "风险测评已过期",
    assessHint: "完成测评后，即可按您的需求匹配和买入产品。约 3 分钟，共 10 道题。",
    start: "开始测评",
    needs: "本次需求",
    needsHint: "在对话中告诉我，这里会自动记录",
    notProvided: "未填写",
    clear: "清空",
    rmTitle: "您的专属理财经理",
    sep: "；",
  },
  en: {
    assets: "Financial assets with us",
    liquid: "Available anytime",
    wealth: "Wealth products",
    toNext: (name: string, gap: string) => `${gap} to ${name}`,
    risk: "Risk profile",
    canBuy: (range: string) => `Eligible for ${range}`,
    validUntil: (d: string) => `Valid until ${d}`,
    retake: "Retake",
    notAssessed: "Risk profile not completed",
    expired: "Risk profile expired",
    assessHint: "Complete the 3-minute, 10-question profile to get matched products and buy.",
    start: "Start now",
    needs: "Your goals",
    needsHint: "Tell me in chat and I'll keep track here",
    notProvided: "Not set",
    clear: "Clear",
    rmTitle: "Your relationship manager",
    sep: ", ",
  },
});

export function riskRange(maxRisk: string) {
  return maxRisk === "PR1" ? "PR1" : `PR1–${maxRisk}`;
}

export function ratingName(state: CustomerState | null, locale: "zh" | "en") {
  const a = state?.assessment;
  if (!a) return null;
  return locale === "en" ? RATING_EN[a.rating] ?? a.rating_name : a.rating_name;
}

/** 深海军蓝资产卡片：总资产、可随时支取、理财持仓、客户等级与升级进度。 */
export function AssetCard({ state, compact = false }: { state: CustomerState | null; compact?: boolean }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const o = state?.profile.overview;
  if (!o) return null;
  return (
    <section aria-label={c.assets} className="flex flex-col gap-3 rounded-card bg-navy p-5 text-white">
      <div className={`flex gap-2 ${compact ? "flex-col items-start" : "items-center justify-between"}`}>
        <span className="text-[13px] text-on-navy-2">{c.assets}</span>
        <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold whitespace-nowrap">
          {o.tier.name}　{o.tier.card_name}
        </span>
      </div>
      <span className={`figures font-extrabold tracking-tight ${compact ? "text-[28px]" : "text-4xl"}`}>
        {formatMoney(o.total, locale)}
      </span>
      {!compact && (
        <div className="flex gap-6 text-[13px]">
          <span className="flex flex-col gap-0.5">
            <span className="text-on-navy-2">{c.liquid}</span>
            <span className="figures font-bold">{formatMoney(o.liquid, locale)}</span>
          </span>
          <span className="flex flex-col gap-0.5">
            <span className="text-on-navy-2">{c.wealth}</span>
            <span className="figures font-bold">{formatMoney(o.wealth, locale)}</span>
          </span>
        </div>
      )}
      {o.next_tier && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-on-navy-2">
            {c.toNext(o.next_tier.name, formatMoney(o.next_tier.gap, locale, 0))}
          </span>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/15">
            <div className="h-full rounded-full bg-white" style={{ width: `${Math.max(o.next_tier.progress * 100, 3)}%` }} />
          </div>
        </div>
      )}
    </section>
  );
}

export function RiskCard({ state, onStart }: { state: CustomerState | null; onStart: () => void }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const a = state?.assessment;
  const expired = state?.gate_reasons.includes("ASSESSMENT_EXPIRED");
  if (!a) {
    return (
      <section className="flex flex-col gap-2 rounded-card bg-notice-soft p-5">
        <span className="font-bold text-notice">{expired ? c.expired : c.notAssessed}</span>
        <p className="text-[13px] leading-6 text-ink-2">{c.assessHint}</p>
        <Button size="sm" onClick={onStart} className="self-start">
          {c.start}
        </Button>
      </section>
    );
  }
  return (
    <section className="flex flex-col gap-1.5 rounded-card bg-fill p-5">
      <span className="text-xs font-bold text-ink-3">{c.risk}</span>
      <span className="flex items-baseline gap-2">
        <span className="text-[26px] font-extrabold">{a.rating}</span>
        <span className="text-[15px] font-bold">{ratingName(state, locale)}</span>
      </span>
      <span className="figures text-[13px] text-ink-2">
        {c.canBuy(riskRange(a.max_product_risk))}
        {c.sep}
        {c.validUntil(formatDate(a.expires_at, locale))}
      </span>
      <button type="button" onClick={onStart} className="self-start text-[13px] font-bold text-brand hover:underline">
        {c.retake}
      </button>
    </section>
  );
}

export function NeedsCard({
  state,
  onChange,
}: {
  state: CustomerState | null;
  onChange: (s: CustomerState) => void;
}) {
  const c = useCopy(COPY);
  const needs = state?.profile.needs ?? [];
  const has = needs.some((n) => n.value);
  return (
    <section className="flex flex-col gap-2 rounded-card bg-fill p-5">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-bold text-ink-3">{c.needs}</span>
        {has && (
          <button type="button" onClick={() => clearNeeds().then(onChange)} className="text-xs font-semibold text-ink-3 hover:text-ink">
            {c.clear}
          </button>
        )}
      </div>
      {!has && <p className="text-[13px] text-ink-3">{c.needsHint}</p>}
      <dl className="figures flex flex-col gap-1.5 text-sm">
        {needs
          .filter((n) => n.value)
          .map((n) => (
            <div key={n.field} className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-2">{n.label}</dt>
              <dd className="text-right font-bold">{n.value}</dd>
            </div>
          ))}
      </dl>
    </section>
  );
}

export function RmRow({ state, onContact }: { state: CustomerState | null; onContact: () => void }) {
  const c = useCopy(COPY);
  const rm = state?.profile.overview?.rm;
  if (!rm) return null;
  return (
    <button type="button" onClick={onContact} className="flex w-full items-center gap-3 rounded-2xl py-2 text-left hover:bg-fill">
      <Avatar text={rm.rm_name.slice(0, 1)} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[15px] font-bold">{rm.rm_name}</span>
        <span className="text-[13px] text-ink-3">{c.rmTitle}</span>
      </span>
      <ChevronRight />
    </button>
  );
}
