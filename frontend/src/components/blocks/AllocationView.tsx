"use client";

import { useProductActions } from "@/components/products/ProductActions";
import { Chip } from "@/components/ui";
import { defineCopy, useCopy, useSeparators } from "@/lib/i18n";
import type { AllocationBlock, NeedsUpdateBlock } from "@/lib/types";

const COLORS = [1, 2, 3, 4, 5].map((i) => `var(--series-${i})`);

const COPY = defineCopy({
  zh: {
    saved: "已记录：",
    passed: "约束检查通过",
    failed: "存在未通过的约束",
    status: { OK: "通过", WARN: "注意", FAIL: "未通过" },
    clickHint: "点击产品名称可查看详情或买入。",
    shares: (parts: string) => `配置比例：${parts}`,
  },
  en: {
    saved: "Saved: ",
    passed: "All checks passed",
    failed: "Some checks failed",
    status: { OK: "Pass", WARN: "Note", FAIL: "Fail" },
    clickHint: "Tap a product name to view details or buy.",
    shares: (parts: string) => `Allocation: ${parts}`,
  },
});

/** A chip after needs are recorded in chat, so the customer knows what the system remembered. */
export function NeedsUpdateNote({ block }: { block: NeedsUpdateBlock }) {
  const c = useCopy(COPY);
  const sep = useSeparators();
  return (
    <span className="inline-flex w-fit max-w-full items-center rounded-full bg-fill px-3 py-1.5 text-xs leading-5 font-semibold text-ink-2">
      {c.saved}
      {block.items.map((i) => `${i.label} ${i.value}`).join(sep.semi)}
    </span>
  );
}

/** Allocation scenario: proportion bar + details + constraint checks. No return projections of any kind. */
export function AllocationView({ block }: { block: AllocationBlock }) {
  const c = useCopy(COPY);
  const sep = useSeparators();
  const { open } = useProductActions();
  const color = (i: number) => COLORS[Math.min(i, COLORS.length - 1)];
  const tone = { OK: "ok", WARN: "notice", FAIL: "danger" } as const;

  return (
    <figure className="flex max-w-2xl flex-col gap-4 rounded-card bg-fill p-5">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[17px] font-extrabold">{block.title}</span>
        <Chip tone={block.passed ? "ok" : "danger"}>{block.passed ? c.passed : c.failed}</Chip>
      </figcaption>

      <div
        className="flex h-3 gap-0.5 overflow-hidden rounded-full"
        role="img"
        aria-label={c.shares(block.slices.map((s) => `${s.name} ${s.pct_text}`).join(sep.clause))}
      >
        {block.slices.map((s, i) => (
          <span key={s.code} style={{ flex: s.amount, background: color(i) }} />
        ))}
      </div>

      <table className="figures w-full text-sm">
        <tbody>
          {block.slices.map((s, i) => (
            <tr key={s.code} className="border-b border-line last:border-0">
              <td className="py-2.5 pr-2">
                <span className="mr-2.5 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: color(i) }} aria-hidden />
                {/* Wealth products open details and purchase; a checking deposit has no risk level and isn't clickable */}
                {s.risk_level ? (
                  <button type="button" onClick={() => open(s.code)} className="text-left font-bold text-brand hover:underline">
                    {s.name}
                  </button>
                ) : (
                  <span className="font-bold">{s.name}</span>
                )}
                <span className="ml-1.5 text-xs text-ink-3">
                  {s.risk_level ? `${s.risk_level}${sep.clause}` : ""}
                  {s.lockup}
                </span>
              </td>
              <td className="py-2.5 text-right font-bold">{s.amount_text}</td>
              <td className="w-16 py-2.5 text-right text-ink-2">{s.pct_text}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="flex flex-col gap-2 text-sm leading-6">
        {block.checks.map((check) => (
          <li key={check.label + check.message} className="flex items-start gap-2.5">
            <Chip tone={tone[check.status]} className="mt-0.5">
              {c.status[check.status]}
            </Chip>
            <span>
              <span className="font-bold">
                {check.label}
                {sep.colon}
              </span>
              <span className="text-ink-2">{check.message}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs leading-5 text-ink-3">
        {c.clickHint}
        {sep.sentence}
        {block.disclaimer}
      </p>
    </figure>
  );
}
