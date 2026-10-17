"use client";

import { useState } from "react";

import { ProductCardView } from "@/components/products/ProductCardView";
import { ProductDetailDialog } from "@/components/products/ProductDetailDialog";
import { ProductDetailView } from "@/components/products/ProductDetailView";
import type { ComparisonTableBlock, ProductDetailBlock, ProductListBlock } from "@/lib/types";

export function ProductListView({ block }: { block: ProductListBlock }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <figure className="max-w-3xl">
      <figcaption className="font-serif text-base font-bold">{block.title}</figcaption>
      {block.items.length === 0 ? (
        <p className="mt-2 text-sm text-ink-2">没有符合条件的产品。</p>
      ) : (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {block.items.map((item) => (
            <li key={item.code}>
              <ProductCardView product={item} onOpen={setOpen} />
            </li>
          ))}
        </ul>
      )}
      <Footnotes excluded={block.excluded} lines={[block.ranking_note, block.disclaimer]} />
      <ProductDetailDialog code={open} onClose={() => setOpen(null)} />
    </figure>
  );
}

export function ProductDetailCard({ block }: { block: ProductDetailBlock }) {
  return (
    <figure className="max-w-2xl rounded-sm border border-rule bg-surface px-5 py-4">
      <figcaption className="mb-3 font-serif text-lg font-bold">{block.name}</figcaption>
      <ProductDetailView product={block} />
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
