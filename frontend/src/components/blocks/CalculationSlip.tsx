"use client";

import { Chip } from "@/components/ui";
import { formatYuan } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { CalculationResultBlock } from "@/lib/types";

const COPY = defineCopy({
  zh: { formula: "公式", hypothetical: "假设情景，非预测、非承诺", assumptions: "测算假设" },
  en: { formula: "Formula", hypothetical: "Hypothetical, not a forecast or promise", assumptions: "Assumptions" },
});

/** 测算结果：大号结果数字 + 明细 + 假设。顶部标签标明这是假设情景。 */
export function CalculationSlip({ block }: { block: CalculationResultBlock }) {
  const c = useCopy(COPY);
  const [headline, ...rows] = block.items;

  return (
    <figure className="flex max-w-xl flex-col gap-4 rounded-card bg-fill p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <figcaption className="text-[17px] font-extrabold">{block.title}</figcaption>
        <Chip tone="notice" className="whitespace-normal" >
          <span title={block.disclaimer}>{c.hypothetical}</span>
        </Chip>
      </div>
      {block.formula && (
        <p className="figures -mt-2 text-sm text-ink-2">
          {c.formula} <span className="font-semibold text-ink">{block.formula}</span>
        </p>
      )}

      {headline && (
        <div>
          <p className="text-sm text-ink-2">{headline.label}</p>
          <p className="figures text-4xl font-extrabold tracking-tight">
            {formatYuan(headline.value)}
            <span className="ml-1.5 text-base font-semibold text-ink-2">{headline.unit}</span>
          </p>
        </div>
      )}

      <dl className="flex flex-col gap-2 text-sm">
        {rows.map((item) => (
          <div key={item.label} className="flex items-baseline gap-2">
            <dt className="text-ink-2">{item.label}</dt>
            <span className="leader" aria-hidden />
            <dd className="figures font-bold">
              {formatYuan(item.value)} {item.unit}
            </dd>
          </div>
        ))}
      </dl>

      <div className="border-t border-line pt-3">
        <p className="text-xs font-bold text-ink-2">{c.assumptions}</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">
          {block.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </div>
    </figure>
  );
}
