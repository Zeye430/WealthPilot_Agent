"use client";

import { useEffect, useState } from "react";

import { ProductCardView } from "@/components/products/ProductCardView";
import { ApiError, getProducts, productRiskRange } from "@/lib/api";
import type { CustomerState, ProductListResponse } from "@/lib/types";

const TYPES = [
  { value: "", label: "全部" },
  { value: "CASH_MANAGEMENT", label: "现金管理类" },
  { value: "FIXED_INCOME", label: "固定收益类" },
  { value: "FIXED_INCOME_PLUS", label: "固收+" },
  { value: "MIXED", label: "混合类" },
  { value: "EQUITY", label: "权益类" },
];

/**
 * 产品页：全部在售产品都可查看（产品负责人决定）。
 * 风险等级范围内的产品排在前面、可以买入；超出等级的只能查看条款。能否买入由后端判断。
 */
export function ProductBrowser({
  state,
  onStartAssessment,
}: {
  state: CustomerState | null;
  onStartAssessment: () => void;
}) {
  const [type, setType] = useState("");
  const [data, setData] = useState<ProductListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rating = state?.assessment?.rating;

  useEffect(() => {
    let cancelled = false;
    getProducts(type || undefined)
      .then((d) => !cancelled && (setData(d), setError(null)))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "产品加载失败"));
    return () => {
      cancelled = true;
    };
  }, [type, rating]);

  const buyable = data?.items.filter((i) => i.purchasable) ?? [];
  const viewOnly = data?.items.filter((i) => !i.purchasable) ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-8">
        <h1 className="font-serif text-2xl font-bold">理财产品</h1>
        {data?.rating ? (
          <p className="mt-2 text-sm text-ink-2">
            您的风险等级为 {data.rating.code} {data.rating.name}，可买入 {productRiskRange(data.rating.max_product_risk)}{" "}
            产品；更高风险等级的产品可以查看条款，但不能买入。
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-sm border border-notice/40 bg-notice-soft px-4 py-3">
            <p className="text-sm text-ink-2">您可以先浏览产品；完成风险测评（约 3 分钟）后即可买入与您风险等级匹配的产品。</p>
            <button
              type="button"
              onClick={onStartAssessment}
              className="rounded-sm bg-brand px-4 py-1.5 text-sm font-medium text-surface"
            >
              开始测评
            </button>
          </div>
        )}

        <div role="tablist" aria-label="产品类型" className="mt-5 flex flex-wrap gap-1.5">
          {TYPES.map((t) => (
            <button
              key={t.value}
              type="button"
              role="tab"
              aria-selected={type === t.value}
              onClick={() => setType(t.value)}
              className={`rounded-sm border px-3 py-1.5 text-sm ${
                type === t.value ? "border-brand bg-brand-soft font-medium text-brand" : "border-rule hover:border-ink-3"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}
        {data && data.items.length === 0 && <p className="mt-6 text-sm text-ink-2">该类型下暂无在售产品。</p>}

        {buyable.length > 0 && (
          <Section title="符合您风险等级的产品" count={buyable.length}>
            {buyable.map((item) => (
              <li key={item.code}>
                <ProductCardView product={item} />
              </li>
            ))}
          </Section>
        )}
        {viewOnly.length > 0 && (
          <Section title={data?.rating ? "超出您的风险等级（仅可查看）" : "在售产品"} count={viewOnly.length}>
            {viewOnly.map((item) => (
              <li key={item.code}>
                <ProductCardView product={item} />
              </li>
            ))}
          </Section>
        )}

        {data && (
          <div className="mt-6 space-y-0.5 text-xs text-ink-3">
            <p>{data.ranking_note}</p>
            <p>理财非存款、产品有风险、投资须谨慎。所有产品均为虚构演示产品；业绩比较基准不是预期收益率。</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="flex items-baseline gap-2 font-serif text-base font-bold">
        {title}
        <span className="figures text-xs font-normal text-ink-3">{count} 款</span>
      </h2>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</ul>
    </section>
  );
}
