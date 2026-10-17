"use client";

import { useEffect, useState } from "react";

import { ProductCardView } from "@/components/products/ProductCardView";
import { ProductDetailDialog } from "@/components/products/ProductDetailDialog";
import { ApiError, getProducts } from "@/lib/api";
import type { CustomerState, ProductListResponse } from "@/lib/types";

const TYPES = [
  { value: "", label: "全部" },
  { value: "CASH_MANAGEMENT", label: "现金管理类" },
  { value: "FIXED_INCOME", label: "固定收益类" },
  { value: "FIXED_INCOME_PLUS", label: "固收+" },
  { value: "MIXED", label: "混合类" },
  { value: "EQUITY", label: "权益类" },
];

/** 产品浏览页：与对话中的产品工具调用同一套接口和适当性规则。 */
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
  const [open, setOpen] = useState<string | null>(null);
  const assessed = state?.permission === "ASSESSED";
  const rating = state?.assessment?.rating;

  useEffect(() => {
    if (!assessed) return;
    let cancelled = false;
    getProducts(type || undefined)
      .then((d) => !cancelled && (setData(d), setError(null)))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "产品加载失败"));
    return () => {
      cancelled = true;
    };
  }, [assessed, type, rating]);

  if (!assessed) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-8">
        <h1 className="font-serif text-2xl font-bold">产品浏览</h1>
        <p className="mt-3 max-w-prose leading-7 text-ink-2">
          根据理财产品销售的适当性要求，完成风险承受能力测评后，才能查看您风险等级范围内的产品。
        </p>
        <button
          type="button"
          onClick={onStartAssessment}
          className="mt-6 rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface"
        >
          开始测评
        </button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-8">
        <h1 className="font-serif text-2xl font-bold">产品浏览</h1>
        {data && (
          <p className="mt-2 text-sm text-ink-2">
            您的评级为 {data.rating.code} {data.rating.name}，以下为 {data.rating.max_product_risk}{" "}
            及以下风险等级的在售产品。
          </p>
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
        {data && data.items.length === 0 && (
          <p className="mt-6 text-sm text-ink-2">该类型下没有您风险等级范围内的在售产品。</p>
        )}
        <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data?.items.map((item) => (
            <li key={item.code}>
              <ProductCardView product={item} onOpen={setOpen} />
            </li>
          ))}
        </ul>
        {data && (
          <div className="mt-4 space-y-0.5 text-xs text-ink-3">
            {data.excluded.length > 0 && (
              <p>未展示：{data.excluded.map((e) => `${e.reason} ${e.count} 款`).join("；")}。</p>
            )}
            <p>{data.ranking_note}</p>
            <p>所有产品均为虚构演示产品，信息不构成投资建议；业绩比较基准不是预期收益率。</p>
          </div>
        )}
      </div>
      <ProductDetailDialog code={open} onClose={() => setOpen(null)} />
    </div>
  );
}
