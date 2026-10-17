"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { AllocationBlock, NeedsUpdateBlock } from "@/lib/types";

const COLORS = [1, 2, 3, 4, 5].map((i) => `var(--series-${i})`);
const STATUS = {
  OK: { label: "通过", className: "text-ink-2", mark: "✓" },
  WARN: { label: "注意", className: "text-notice", mark: "!" },
  FAIL: { label: "未通过", className: "text-danger", mark: "✗" },
} as const;

/** 对话中记录需求后的一行确认，让客户知道系统记住了什么。 */
export function NeedsUpdateNote({ block }: { block: NeedsUpdateBlock }) {
  return (
    <p className="text-xs text-ink-2">
      已记录您的需求：{block.items.map((i) => `${i.label} ${i.value}`).join("；")}
    </p>
  );
}

/** 配置情景：构成环形图 + 明细 + 约束检查。不展示任何收益测算。 */
export function AllocationView({ block }: { block: AllocationBlock }) {
  // 超过 5 项时，图中合并为「其他」（配色只有 5 种已验证的色盲可分辨颜色）；明细表仍列全部
  const chart =
    block.slices.length <= COLORS.length
      ? block.slices
      : [
          ...block.slices.slice(0, COLORS.length - 1),
          {
            ...block.slices[COLORS.length - 1],
            code: "OTHER",
            name: "其他",
            amount: block.slices.slice(COLORS.length - 1).reduce((s, x) => s + x.amount, 0),
          },
        ];

  return (
    <figure className="max-w-2xl rounded-sm border border-rule bg-surface px-5 py-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="font-serif text-base font-bold">{block.title}</span>
        <span className={`text-xs font-medium ${block.passed ? "text-ink-2" : "text-danger"}`}>
          {block.passed ? "约束检查通过" : "存在未通过的约束"}
        </span>
      </figcaption>

      <div className="mt-3 grid items-center gap-4 sm:grid-cols-[180px_1fr]">
        <div className="mx-auto h-44 w-44">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chart}
                dataKey="amount"
                nameKey="name"
                innerRadius="58%"
                outerRadius="95%"
                paddingAngle={1}
                stroke="var(--surface)"
                strokeWidth={2}
                isAnimationActive={false}
              >
                {chart.map((s, i) => (
                  <Cell key={s.code} fill={COLORS[i]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value, name) => [`${Number(value).toLocaleString("zh-CN")} 元`, name]}
                contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)", fontSize: 12 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <table className="figures w-full text-sm">
          <tbody>
            {block.slices.map((s, i) => (
              <tr key={s.code} className="border-b border-rule last:border-0">
                <td className="py-1.5 pr-2">
                  <span
                    className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle"
                    style={{ background: COLORS[Math.min(i, COLORS.length - 1)] }}
                    aria-hidden
                  />
                  {s.name}
                  <span className="ml-1.5 text-xs text-ink-3">
                    {s.risk_level ? `${s.risk_level}，` : ""}
                    {s.lockup}
                  </span>
                </td>
                <td className="py-1.5 text-right">{s.amount_text}</td>
                <td className="w-16 py-1.5 text-right text-ink-2">{s.pct_text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="mt-3 space-y-1.5 border-t border-rule pt-3 text-sm">
        {block.checks.map((c) => {
          const st = STATUS[c.status];
          return (
            <li key={c.label + c.message} className="flex gap-2">
              <span className={`w-12 shrink-0 text-xs font-medium ${st.className}`}>
                {st.mark} {st.label}
              </span>
              <span className="leading-6">
                <span className="font-medium">{c.label}：</span>
                <span className="text-ink-2">{c.message}</span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-ink-3">{block.disclaimer}</p>
    </figure>
  );
}
