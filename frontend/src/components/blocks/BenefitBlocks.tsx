"use client";

import { UpcomingCard } from "@/components/products/UpcomingCard";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { TierBenefitsBlock, UpcomingProductsBlock } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    upcoming: "即将发售的新品",
    aum: (v: string) => `金融资产约 ${v}`,
    toNext: (name: string, threshold: string, gap: string) => `距${name}（${threshold}）还差 ${gap}`,
    progress: (name: string) => `距${name}的进度`,
    projection: (aum: string, tier: string) => `如计划资金为新转入本行的资金，金融资产将约为 ${aum}，可达到${tier}标准。`,
    current: "当前权益",
    nextBenefits: (name: string) => `${name}权益`,
    campaigns: "可参与的活动",
  },
  en: {
    upcoming: "Coming soon",
    aum: (v: string) => `Financial assets about ${v}`,
    toNext: (name: string, threshold: string, gap: string) => `${gap} to ${name} (${threshold})`,
    progress: (name: string) => `Progress to ${name}`,
    projection: (aum: string, tier: string) => `If this is new money moved to the bank, your assets would be about ${aum}, meeting the ${tier} level.`,
    current: "Your benefits",
    nextBenefits: (name: string) => `${name} benefits`,
    campaigns: "Current offers",
  },
});

/** New-product cards in chat: only products matching the customer's criteria, with "remind me". */
export function UpcomingProductsView({ block }: { block: UpcomingProductsBlock }) {
  const c = useCopy(COPY);
  return (
    <figure className="flex max-w-3xl flex-col gap-3">
      <figcaption className="text-[17px] font-extrabold">{c.upcoming}</figcaption>
      <ul className="scroll-row -mx-5 flex gap-3 overflow-x-auto px-5 pb-1 lg:mx-0 lg:grid lg:grid-cols-2 lg:overflow-visible lg:px-0">
        {block.items.map((item) => (
          <li key={item.code} className="w-[280px] shrink-0 lg:w-auto">
            <UpcomingCard product={item} reminded={item.reminded} />
          </li>
        ))}
      </ul>
      <p className="text-xs leading-5 text-ink-3">
        {block.note}
        {block.disclaimer}
      </p>
    </figure>
  );
}

/**
 * Customer tier and benefits: a deep navy card shows the tier and progress, with benefits and current campaigns listed below.
 * Tiers are based on total financial assets (deposits included), never tied to a specific product.
 */
export function TierBenefitsView({ block }: { block: TierBenefitsBlock }) {
  const c = useCopy(COPY);
  const next = block.next_tier;
  return (
    <figure className="flex max-w-xl flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-card bg-navy p-5 text-white">
        <figcaption className="flex items-baseline justify-between gap-3">
          <span className="text-xl font-extrabold">{block.tier.name}</span>
          <span className="text-xs text-on-navy-2">{block.tier.card_name}</span>
        </figcaption>
        <span className="figures text-sm text-on-navy-2">{c.aum(block.aum)}</span>
        {next && (
          <div className="flex flex-col gap-1.5">
            <span className="figures text-xs text-on-navy-2">{c.toNext(next.name, next.threshold, next.gap)}</span>
            <div
              className="h-1.5 overflow-hidden rounded-full bg-white/15"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(next.progress * 100)}
              aria-label={c.progress(next.name)}
            >
              <div className="h-full rounded-full bg-white" style={{ width: `${Math.max(next.progress * 100, 3)}%` }} />
            </div>
          </div>
        )}
      </div>
      {block.projection?.reaches_next && (
        <p className="rounded-2xl bg-brand-soft px-4 py-3 text-sm leading-6 text-brand-strong">
          {c.projection(block.projection.aum, block.projection.tier_name)}
        </p>
      )}

      <div className={`grid gap-3 ${next ? "sm:grid-cols-2" : ""}`}>
        <BenefitList title={c.current} items={block.benefits} />
        {next && <BenefitList title={c.nextBenefits(next.name)} items={next.benefits} muted />}
      </div>

      {block.campaigns.length > 0 && (
        <section className="flex flex-col gap-2 rounded-card bg-fill p-5">
          <h3 className="text-[15px] font-extrabold">{c.campaigns}</h3>
          <ul className="flex flex-col gap-3 text-sm">
            {block.campaigns.map((cp) => (
              <li key={cp.name}>
                <p className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-bold">{cp.name}</span>
                  <span className="figures text-xs text-ink-3">{cp.period}</span>
                </p>
                <p className="text-ink-2">{cp.reward}</p>
                <p className="mt-0.5 text-xs leading-5 text-ink-3">{cp.rule}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="text-xs leading-5 text-ink-3">{block.evaluation_rule}</p>
    </figure>
  );
}

function BenefitList({ title, items, muted = false }: { title: string; items: string[]; muted?: boolean }) {
  return (
    <section className="rounded-card bg-fill p-5">
      <h3 className="text-xs font-bold text-ink-3">{title}</h3>
      <ul className={`mt-2 flex flex-col gap-1.5 text-sm leading-6 ${muted ? "text-ink-2" : "font-semibold"}`}>
        {items.map((b) => (
          <li key={b} className="flex gap-2">
            <span aria-hidden className={`mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full ${muted ? "bg-ink-3" : "bg-brand"}`} />
            {b}
          </li>
        ))}
      </ul>
    </section>
  );
}
