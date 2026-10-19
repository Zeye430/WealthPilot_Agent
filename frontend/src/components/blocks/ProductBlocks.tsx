"use client";

import { useState } from "react";

import { useProductActions } from "@/components/products/ProductActions";
import { ProductCardView } from "@/components/products/ProductCardView";
import { ProductDetailView } from "@/components/products/ProductDetailView";
import { Button, Chip } from "@/components/ui";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { ComparisonTableBlock, ProductDetailBlock, ProductListBlock } from "@/lib/types";

/** 对话中先展示匹配度最高的 3 款，其余折叠，避免一次给客户太多选择。 */
const FIRST_SHOWN = 3;

const COPY = defineCopy({
  zh: {
    none: "没有符合条件的产品。",
    more: (n: number) => `查看其余 ${n} 款`,
    notShown: "未展示：",
    count: (n: number) => `${n} 款`,
    inRange: "在您的风险等级范围内",
    outOfRange: "超出您的风险等级，仅可查看",
    buy: "买入",
    compare: "产品对比",
    item: "项目",
  },
  en: {
    none: "No products match these conditions.",
    more: (n: number) => `Show ${n} more`,
    notShown: "Not shown: ",
    count: (n: number) => `${n}`,
    inRange: "Within your risk level",
    outOfRange: "Above your risk level. View only.",
    buy: "Buy",
    compare: "Comparison",
    item: "Item",
  },
});

export function ProductListView({ block }: { block: ProductListBlock }) {
  const c = useCopy(COPY);
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? block.items : block.items.slice(0, FIRST_SHOWN);
  const hidden = block.items.length - shown.length;
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="text-[17px] font-extrabold">{block.title}</figcaption>
      {block.items.length === 0 ? (
        <p className="text-sm text-ink-2">{c.none}</p>
      ) : (
        <ul className="scroll-row -mx-5 flex snap-x snap-mandatory gap-3 overflow-x-auto px-5 pb-1 lg:mx-0 lg:grid lg:grid-cols-2 lg:overflow-visible lg:px-0">
          {shown.map((item) => (
            <li key={item.code} className="w-[264px] shrink-0 snap-start lg:w-auto">
              <ProductCardView product={item} />
            </li>
          ))}
        </ul>
      )}
      {hidden > 0 && (
        <Button variant="quiet" size="sm" onClick={() => setExpanded(true)} className="self-start">
          {c.more(hidden)}
        </Button>
      )}
      <Footnotes excluded={block.excluded} lines={[block.ranking_note, block.disclaimer]} />
    </figure>
  );
}

export function ProductDetailCard({ block }: { block: ProductDetailBlock }) {
  const c = useCopy(COPY);
  const { open } = useProductActions();
  return (
    <figure className="flex max-w-2xl flex-col gap-4 rounded-card bg-fill p-5">
      <figcaption className="text-lg font-extrabold">{block.name}</figcaption>
      <ProductDetailView product={block} />
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <Chip tone={block.eligible ? "ok" : "notice"}>{block.eligible ? c.inRange : c.outOfRange}</Chip>
        {block.eligible && <Button onClick={() => open(block.code)}>{c.buy}</Button>}
      </div>
    </figure>
  );
}

export function ComparisonTableView({ block }: { block: ComparisonTableBlock }) {
  const c = useCopy(COPY);
  return (
    <figure className="flex max-w-3xl flex-col gap-3">
      <figcaption className="text-[17px] font-extrabold">{c.compare}</figcaption>
      <div className="overflow-x-auto rounded-card bg-fill">
        <table className="figures w-full min-w-[32rem] border-collapse text-sm">
          <thead>
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-ink-3">{c.item}</th>
              {block.columns.map((col) => (
                <th key={col.code} className="px-4 py-3 text-left font-extrabold">
                  {col.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row) => (
              <tr key={row.label} className={`border-t border-line ${row.metric ? "bg-brand-soft/60" : ""}`}>
                <th className="px-4 py-2.5 text-left font-medium text-ink-2">{row.label}</th>
                {row.values.map((v, i) => (
                  <td key={i} className={`px-4 py-2.5 align-top ${v === "—" ? "text-ink-3" : "font-semibold"}`}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.notes.map((n) => (
        <p key={n} className="rounded-2xl bg-notice-soft px-4 py-2.5 text-xs leading-5 text-notice">
          {n}
        </p>
      ))}
      <Footnotes lines={[block.disclaimer]} />
    </figure>
  );
}

function Footnotes({ excluded = [], lines }: { excluded?: { reason: string; count: number }[]; lines: string[] }) {
  const c = useCopy(COPY);
  return (
    <div className="flex flex-col gap-0.5 text-xs leading-5 text-ink-3">
      {excluded.length > 0 && (
        <p>
          {c.notShown}
          {excluded.map((e) => `${e.reason} ${c.count(e.count)}`).join("；")}
        </p>
      )}
      {lines.map((l) => (
        <p key={l}>{l}</p>
      ))}
    </div>
  );
}
