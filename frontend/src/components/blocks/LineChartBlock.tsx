"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { formatWan, formatYuan } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { LineChartBlock as Block } from "@/lib/types";

const COPY = defineCopy({
  zh: { table: "查看数据表", yuan: "（元）", point: (x: string | number, unit: string) => `第 ${x} ${unit}`, unit: "元" },
  en: { table: "View data table", yuan: " (CNY)", point: (x: string | number, unit: string) => `${unit} ${x}`, unit: "CNY" },
});

// 颜色按系列顺序固定分配（已用 dataviz 校验脚本验证色盲可分辨），最多 5 条
const SERIES_COLORS = [1, 2, 3, 4, 5].map((i) => `var(--series-${i})`);

export function LineChartBlock({ block }: { block: Block }) {
  const c = useCopy(COPY);
  const series = block.series.slice(0, SERIES_COLORS.length);
  const xs = series[0]?.points.map((p) => p.x) ?? [];
  const data = xs.map((x, i) => ({
    x,
    ...Object.fromEntries(series.map((s) => [s.name, s.points[i]?.y])),
  }));
  const multi = series.length > 1;
  const last = xs.length - 1;

  return (
    <figure className="max-w-xl rounded-card bg-fill px-3 pt-5 pb-4 sm:px-5">
      <figcaption className="px-2 text-[17px] font-extrabold">{block.title}</figcaption>
      <div className="mt-3 h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: multi ? 64 : 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="x"
              tickFormatter={(x) => `${x}${block.x_label}`}
              tick={{ fill: "var(--ink-3)", fontSize: 12 }}
              axisLine={{ stroke: "var(--line)" }}
              tickLine={false}
            />
            <YAxis
              tickFormatter={formatWan}
              tick={{ fill: "var(--ink-3)", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={56}
              domain={["auto", "auto"]}
            />
            <Tooltip
              content={(props) => <ChartTooltip {...props} xLabel={block.x_label} />}
              cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }}
            />
            {multi && (
              <Legend
                verticalAlign="top"
                align="left"
                iconType="plainline"
                wrapperStyle={{ fontSize: 12, paddingBottom: 8 }}
                formatter={(value) => <span style={{ color: "var(--ink-2)" }}>{value}</span>}
              />
            )}
            {series.map((s, i) => (
              <Line
                key={s.name}
                dataKey={s.name}
                stroke={SERIES_COLORS[i]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: "var(--fill)", strokeWidth: 2 }}
                isAnimationActive={false}
                label={
                  multi && series.length <= 4
                    ? ({ x, y, index }) =>
                        index === last ? (
                          <text x={Number(x) + 6} y={Number(y)} dy={4} fontSize={12} fill="var(--ink-2)">
                            {s.name.replace("年化 ", "")}
                          </text>
                        ) : null
                    : undefined
                }
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {block.note && <p className="mt-1 px-2 text-xs text-ink-3">{block.note}</p>}
      <details className="mt-2 px-2 text-xs text-ink-2">
        <summary className="cursor-pointer font-semibold select-none">{c.table}</summary>
        <div className="mt-2 max-h-56 overflow-auto">
          <table className="figures w-full text-right">
            <thead className="text-ink-3">
              <tr>
                <th className="py-1 text-left font-normal">{block.x_label}</th>
                {series.map((s) => (
                  <th key={s.name} className="py-1 font-normal">
                    {s.name}
                    {c.yuan}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.x} className="border-t border-line">
                  <td className="py-1 text-left">{row.x}</td>
                  {series.map((s) => (
                    <td key={s.name} className="py-1">
                      {formatYuan((row as Record<string, number>)[s.name])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
  xLabel,
}: TooltipContentProps & { xLabel: string }) {
  const c = useCopy(COPY);
  if (!active || !payload?.length) return null;
  return (
    <div className="figures rounded-2xl bg-surface px-3 py-2 text-xs shadow-[0_4px_20px_rgba(10,31,61,0.12)]">
      <p className="mb-1 text-ink-2">{c.point(String(label), xLabel)}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-ink">
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
          <span className="text-ink-2">{p.name}</span>
          <span className="ml-auto pl-3 font-bold">
            {formatYuan(Number(p.value))} {c.unit}
          </span>
        </p>
      ))}
    </div>
  );
}
