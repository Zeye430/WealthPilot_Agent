"use client";

import { useEffect, useState } from "react";

import { ratingName, riskRange } from "@/components/Profile";
import { ProductCardView } from "@/components/products/ProductCardView";
import { UpcomingCard } from "@/components/products/UpcomingCard";
import { Button } from "@/components/ui";
import { ApiError, getProducts } from "@/lib/api";
import { defineCopy, useCopy, useLocale } from "@/lib/i18n";
import type { CustomerState, ProductListResponse } from "@/lib/types";

const TYPES = ["", "CASH_MANAGEMENT", "FIXED_INCOME", "FIXED_INCOME_PLUS", "MIXED", "EQUITY"] as const;

const COPY = defineCopy({
  zh: {
    title: "理财产品",
    types: { "": "全部", CASH_MANAGEMENT: "现金管理类", FIXED_INCOME: "固定收益类", FIXED_INCOME_PLUS: "固收+", MIXED: "混合类", EQUITY: "权益类" } as Record<(typeof TYPES)[number], string>,
    ratingLine: (code: string, name: string, range: string) => `您的风险等级为 ${code} ${name}，可买入 ${range} 产品；更高风险等级的产品可以查看条款，但不能买入。`,
    browseHint: "您可以先浏览产品；完成风险测评（约 3 分钟）后即可买入与您风险等级匹配的产品。",
    start: "开始测评",
    empty: "该类型下暂无在售产品。",
    upcoming: "即将发售",
    buyable: "符合您风险等级的产品",
    aboveRating: "超出您的风险等级（仅可查看）",
    onSale: "在售产品",
    count: (n: number) => `${n} 款`,
    footer: "理财非存款、产品有风险、投资须谨慎。所有产品均为虚构演示产品；业绩比较基准不是预期收益率。",
    loadFailed: "产品加载失败",
    filter: "产品类型",
  },
  en: {
    title: "Products",
    types: { "": "All", CASH_MANAGEMENT: "Cash management", FIXED_INCOME: "Fixed income", FIXED_INCOME_PLUS: "Fixed income+", MIXED: "Mixed", EQUITY: "Equity" } as Record<(typeof TYPES)[number], string>,
    ratingLine: (code: string, name: string, range: string) => `Your risk level is ${code} ${name}. You can buy ${range} products; higher-risk products are view-only.`,
    browseHint: "Browse freely. Complete the 3-minute risk profile to buy products that match your risk level.",
    start: "Start now",
    empty: "No products of this type are on sale.",
    upcoming: "Coming soon",
    buyable: "Within your risk level",
    aboveRating: "Above your risk level (view only)",
    onSale: "On sale",
    count: (n: number) => `${n}`,
    footer: "Wealth products are not deposits and involve risk. All products are fictional; a benchmark is not an expected return.",
    loadFailed: "Couldn't load products",
    filter: "Product type",
  },
});

/**
 * 产品页：全部在售产品都可查看（产品负责人决定）。
 * 风险等级范围内的产品排在前面、可以买入；超出等级的只能查看条款。能否买入由后端判断。
 */
export function ProductBrowser({ state, onStartAssessment }: { state: CustomerState | null; onStartAssessment: () => void }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const [type, setType] = useState<(typeof TYPES)[number]>("");
  const [data, setData] = useState<ProductListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rating = state?.assessment?.rating;

  useEffect(() => {
    let cancelled = false;
    getProducts(type || undefined)
      .then((d) => !cancelled && (setData(d), setError(null)))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : c.loadFailed));
    return () => {
      cancelled = true;
    };
  }, [type, rating, c.loadFailed]);

  const buyable = data?.items.filter((i) => i.purchasable) ?? [];
  const viewOnly = data?.items.filter((i) => !i.purchasable) ?? [];

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-5 px-5 pt-2 pb-10 lg:px-10 lg:pt-8">
        <h1 className="hidden text-[28px] font-extrabold tracking-tight lg:block">{c.title}</h1>
        {data?.rating ? (
          <p className="text-sm leading-6 text-ink-2">
            {c.ratingLine(data.rating.code, ratingName(state, locale) ?? data.rating.name, riskRange(data.rating.max_product_risk))}
          </p>
        ) : (
          <div className="flex flex-col gap-3 rounded-card bg-notice-soft p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm leading-6 text-notice">{c.browseHint}</p>
            <Button size="sm" onClick={onStartAssessment}>
              {c.start}
            </Button>
          </div>
        )}

        <div role="tablist" aria-label={c.filter} className="scroll-row -mx-5 flex gap-2 overflow-x-auto px-5 lg:mx-0 lg:flex-wrap lg:px-0">
          {TYPES.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={type === t}
              onClick={() => setType(t)}
              className={`h-9 shrink-0 rounded-full px-4 text-sm font-bold whitespace-nowrap ${
                type === t ? "bg-ink text-canvas" : "bg-fill text-ink hover:bg-line"
              }`}
            >
              {c.types[t]}
            </button>
          ))}
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
        {data && data.items.length === 0 && data.upcoming.length === 0 && <p className="text-sm text-ink-2">{c.empty}</p>}

        {data && data.upcoming.length > 0 && (
          <Section title={c.upcoming} count={c.count(data.upcoming.length)}>
            {data.upcoming.map((item) => (
              <li key={item.code}>
                <UpcomingCard product={item} reminded={item.remind.reminded} remindAllowed={item.remind.allowed} reason={item.remind.reason} />
              </li>
            ))}
          </Section>
        )}
        {buyable.length > 0 && (
          <Section title={c.buyable} count={c.count(buyable.length)}>
            {buyable.map((item) => (
              <li key={item.code}>
                <ProductCardView product={item} />
              </li>
            ))}
          </Section>
        )}
        {viewOnly.length > 0 && (
          <Section title={data?.rating ? c.aboveRating : c.onSale} count={c.count(viewOnly.length)}>
            {viewOnly.map((item) => (
              <li key={item.code}>
                <ProductCardView product={item} />
              </li>
            ))}
          </Section>
        )}

        {data && (
          <div className="flex flex-col gap-0.5 text-xs leading-5 text-ink-3">
            <p>{data.ranking_note}</p>
            <p>{c.footer}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="flex items-baseline gap-2 text-[17px] font-extrabold">
        {title}
        <span className="figures text-sm font-semibold text-ink-3">{count}</span>
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</ul>
    </section>
  );
}
