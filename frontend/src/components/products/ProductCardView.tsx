"use client";

import { useProductActions } from "@/components/products/ProductActions";
import { Chip } from "@/components/ui";
import { defineCopy, useCopy, useSeparators } from "@/lib/i18n";
import type { ProductCard } from "@/lib/types";

const COPY = defineCopy({
  zh: { open: "查看详情 / 买入", viewOnly: "仅可查看", fictional: (code: string) => `虚构演示产品 ${code}`, asOf: (d: string) => `（${d}）` },
  en: { open: "View / Buy", viewOnly: "View only", fictional: (code: string) => `Fictional demo product ${code}`, asOf: (d: string) => ` (${d})` },
});

/** 产品卡片：对话中的产品列表与「理财产品」页共用，点击打开详情与买入。收益数字始终带口径标签。 */
export function ProductCardView({ product }: { product: ProductCard }) {
  const c = useCopy(COPY);
  const sep = useSeparators();
  const { open } = useProductActions();
  const viewOnly = product.purchasable === false;
  const showWarnings = viewOnly || product.data_quality === "UNVERIFIED";
  // 「1.42%（截至 10-16）」/「1.42% (as of Oct 16)」：大字只放数值，截止日期并入口径标签
  const [, value = product.metric.text, asOf] = product.metric.text.match(/^(.+?)\s*[（(](.+)[）)]$/) ?? [];

  return (
    <button
      type="button"
      onClick={() => open(product.code)}
      className="flex h-full w-full flex-col gap-3 rounded-card bg-fill p-5 text-left transition-colors hover:bg-line/70"
    >
      <span className="flex items-start justify-between gap-3">
        <span className="text-base leading-snug font-extrabold">{product.name}</span>
        <span className="figures shrink-0 rounded-full bg-canvas px-2 py-0.5 text-[11px] font-extrabold" title={product.risk_note ?? undefined}>
          {product.risk_level}
        </span>
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="text-xs text-ink-3">
          {product.metric.label}
          {asOf && c.asOf(asOf)}
        </span>
        <span className="figures text-[26px] leading-tight font-extrabold tracking-tight">{value}</span>
      </span>
      <span className="text-xs text-ink-2">
        {[product.type_label, product.lockup, product.minimum].join(sep.semi)}
      </span>
      {product.highlights && product.highlights.length > 0 && (
        <span className="flex flex-wrap gap-1.5">
          {product.highlights.map((h) => (
            <Chip key={h}>{h}</Chip>
          ))}
        </span>
      )}
      {showWarnings &&
        product.warnings?.map((w) => (
          <span key={w} className="rounded-2xl bg-notice-soft px-3 py-2 text-xs leading-5 text-notice">
            {w}
          </span>
        ))}
      <span className="mt-auto flex flex-col gap-2 pt-1">
        <span
          className={`flex h-11 items-center justify-center rounded-full text-[15px] font-bold ${
            viewOnly ? "bg-canvas text-ink-3" : "bg-brand text-on-brand"
          }`}
        >
          {viewOnly ? c.viewOnly : c.open}
        </span>
        <span className="text-center text-[11px] text-ink-3">{c.fictional(product.code)}</span>
      </span>
    </button>
  );
}
