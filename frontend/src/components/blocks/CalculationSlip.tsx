import { formatYuan } from "@/lib/api";
import type { CalculationResultBlock } from "@/lib/types";

/** 测算凭证：计算结果以银行凭证的形式呈现，角上的印章标明这是假设情景。 */
export function CalculationSlip({ block }: { block: CalculationResultBlock }) {
  const [headline, ...rows] = block.items;

  return (
    <figure className="relative max-w-xl overflow-hidden rounded-sm border border-rule bg-surface">
      <div className="px-5 pt-4 pb-3 sm:px-6">
        <figcaption className="font-serif text-base font-bold">{block.title}</figcaption>
        {block.formula && (
          <p className="figures mt-1 text-sm text-ink-2">
            公式 <span className="text-ink">{block.formula}</span>
          </p>
        )}

        <Stamp text={block.disclaimer} />

        {headline && (
          <div className="mt-4">
            <p className="text-sm text-ink-2">{headline.label}</p>
            <p className="figures font-serif text-3xl font-bold tracking-tight sm:text-4xl">
              {formatYuan(headline.value)}
              <span className="ml-1 font-sans text-base font-normal text-ink-2">
                {headline.unit}
              </span>
            </p>
          </div>
        )}

        <dl className="mt-3 space-y-1.5 text-sm">
          {rows.map((item) => (
            <div key={item.label} className="flex items-baseline gap-2">
              <dt className="text-ink-2">{item.label}</dt>
              <span className="leader" aria-hidden />
              <dd className="figures text-ink">
                {formatYuan(item.value)} {item.unit}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="perforation" aria-hidden />

      <div className="px-5 pt-2 pb-4 sm:px-6">
        <p className="text-xs font-medium text-ink-2">测算假设</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-ink-2">
          {block.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </div>
    </figure>
  );
}

function Stamp({ text }: { text: string }) {
  return (
    <div
      className="pointer-events-none absolute top-4 right-4 flex -rotate-12 flex-col items-center rounded-full border-2 border-brand px-3 py-1.5 text-brand opacity-80 sm:top-5 sm:right-6"
      role="note"
      aria-label={text}
      title={text}
    >
      <span className="font-serif text-sm font-bold leading-tight">假设情景</span>
      <span className="text-[10px] leading-tight">非预测 非承诺</span>
    </div>
  );
}
