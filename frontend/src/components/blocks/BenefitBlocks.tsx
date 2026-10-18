import { UpcomingCard } from "@/components/products/UpcomingCard";
import type { TierBenefitsBlock, UpcomingProductsBlock } from "@/lib/types";

/** 对话中的新品卡片：只展示符合客户条件的新品，附「开售提醒我」。 */
export function UpcomingProductsView({ block }: { block: UpcomingProductsBlock }) {
  return (
    <figure className="max-w-3xl">
      <figcaption className="font-serif text-base font-bold">即将发售的新品</figcaption>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {block.items.map((item) => (
          <li key={item.code}>
            <UpcomingCard product={item} reminded={item.reminded} />
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink-3">
        {block.note}
        {block.disclaimer}
      </p>
    </figure>
  );
}

/**
 * 客户等级与权益：当前等级、距下一等级的进度、权益与在期活动。
 * 等级按金融资产总额评定（存款也计入），不与某款产品挂钩。
 */
export function TierBenefitsView({ block }: { block: TierBenefitsBlock }) {
  const next = block.next_tier;
  return (
    <figure className="max-w-xl rounded-sm border border-rule bg-surface px-5 py-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span>
          <span className="font-serif text-lg font-bold text-brand">{block.tier.name}</span>
          <span className="ml-2 text-xs text-ink-2">{block.tier.card_name}</span>
        </span>
        <span className="figures text-xs text-ink-2">金融资产约 {block.aum}</span>
      </figcaption>

      {next && (
        <div className="mt-3">
          <div className="flex justify-between text-xs text-ink-2">
            <span>
              距{next.name}（{next.threshold}）还差 <span className="figures text-ink">{next.gap}</span>
            </span>
          </div>
          <div
            className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(next.progress * 100)}
            aria-label={`距${next.name}的进度`}
          >
            <div className="h-full rounded-full bg-brand" style={{ width: `${Math.max(next.progress * 100, 2)}%` }} />
          </div>
        </div>
      )}
      {block.projection?.reaches_next && (
        <p className="mt-2 text-sm leading-6">
          如计划资金为新转入本行的资金，金融资产将约为 <span className="figures">{block.projection.aum}</span>，可达到
          <span className="font-medium">{block.projection.tier_name}</span>标准。
        </p>
      )}

      <div className={`mt-4 grid gap-4 ${next ? "sm:grid-cols-2" : ""}`}>
        <BenefitList title="当前权益" items={block.benefits} />
        {next && <BenefitList title={`${next.name}权益`} items={next.benefits} muted />}
      </div>

      {block.campaigns.length > 0 && (
        <section className="mt-4 border-t border-rule pt-3">
          <h3 className="text-sm font-medium">可参与的活动</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {block.campaigns.map((c) => (
              <li key={c.name}>
                <p>
                  <span className="font-medium">{c.name}</span>
                  <span className="ml-2 text-xs text-ink-3">{c.period}</span>
                </p>
                <p className="text-ink-2">{c.reward}</p>
                <p className="mt-0.5 text-xs leading-5 text-ink-3">{c.rule}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="mt-3 text-xs leading-5 text-ink-3">{block.evaluation_rule}</p>
    </figure>
  );
}

function BenefitList({ title, items, muted = false }: { title: string; items: string[]; muted?: boolean }) {
  return (
    <section>
      <h3 className="text-xs font-medium text-ink-2">{title}</h3>
      <ul className={`mt-1.5 space-y-1 text-sm leading-6 ${muted ? "text-ink-2" : ""}`}>
        {items.map((b) => (
          <li key={b} className="flex gap-1.5">
            <span aria-hidden className={muted ? "text-ink-3" : "text-brand"}>
              ·
            </span>
            {b}
          </li>
        ))}
      </ul>
    </section>
  );
}
