"use client";

import { useState } from "react";

import { useProductActions } from "@/components/products/ProductActions";
import { ProductCardView } from "@/components/products/ProductCardView";
import { ProductDetailView } from "@/components/products/ProductDetailView";
import type { ComparisonTableBlock, ProductDetailBlock, ProductListBlock } from "@/lib/types";

/** 对话中最多先展示匹配度最高的 3 款，其余折叠，避免一次给客户太多选择。 */
const FIRST_SHOWN = 3;

export function ProductListView({ block }: { block: ProductListBlock }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? block.items : block.items.slice(0, FIRST_SHOWN);
  const hidden = block.items.length - shown.length;
  return (
    <figure className="max-w-3xl">
      <figcaption className="font-serif text-base font-bold">{block.title}</figcaption>
      {block.items.length === 0 ? (
        <p className="mt-2 text-sm text-ink-2">没有符合条件的产品。</p>
      ) : (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {shown.map((item) => (
            <li key={item.code}>
              <ProductCardView product={item} />
            </li>
          ))}
        </ul>
      )}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-sm text-brand underline underline-offset-4"
        >
          查看其余 {hidden} 款
        </button>
      )}
      <Footnotes excluded={block.excluded} lines={[block.ranking_note, block.disclaimer]} />
    </figure>
  );
}

export function ProductDetailCard({ block }: { block: ProductDetailBlock }) {
  const { open } = useProductActions();
  return (
    <figure className="max-w-2xl rounded-sm border border-rule bg-surface px-5 py-4">
      <figcaption className="mb-3 font-serif text-lg font-bold">{block.name}</figcaption>
      <ProductDetailView product={block} />
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-rule pt-3">
        <p className="text-xs text-ink-3">{block.eligible ? "在您的风险等级范围内" : "超出您的风险等级，仅可查看"}</p>
        {block.eligible && (
          <button
            type="button"
            onClick={() => open(block.code)}
            className="rounded-sm bg-brand px-5 py-2 text-sm font-medium text-surface"
          >
            买入
          </button>
        )}
      </div>
    </figure>
  );
}

export function ComparisonTableView({ block }: { block: ComparisonTableBlock }) {
  return (
    <figure className="max-w-3xl">
      <figcaption className="font-serif text-base font-bold">产品对比</figcaption>
      <div className="mt-3 overflow-x-auto rounded-sm border border-rule bg-surface">
        <table className="figures w-full min-w-[32rem] border-collapse text-sm">
          <thead>
            <tr className="bg-paper">
              <th className="px-3 py-2 text-left font-normal text-ink-3">项目</th>
              {block.columns.map((c) => (
                <th key={c.code} className="px-3 py-2 text-left font-serif font-bold">
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row) => (
              <tr key={row.label} className={`border-t border-rule ${row.metric ? "bg-brand-soft/40" : ""}`}>
                <th className="px-3 py-2 text-left font-normal text-ink-2">{row.label}</th>
                {row.values.map((v, i) => (
                  <td key={i} className={`px-3 py-2 align-top ${v === "—" ? "text-ink-3" : ""}`}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.notes.map((n) => (
        <p key={n} className="mt-2 border-l-2 border-notice bg-notice-soft px-3 py-1.5 text-xs text-ink-2">
          {n}
        </p>
      ))}
      <Footnotes lines={[block.disclaimer]} />
    </figure>
  );
}

function Footnotes({
  excluded = [],
  lines,
}: {
  excluded?: { reason: string; count: number }[];
  lines: string[];
}) {
  return (
    <div className="mt-2 space-y-0.5 text-xs text-ink-3">
      {excluded.length > 0 && (
        <p>
          未展示：
          {excluded.map((e) => `${e.reason} ${e.count} 款`).join("；")}。
        </p>
      )}
      {lines.map((l) => (
        <p key={l}>{l}</p>
      ))}
    </div>
  );
}
