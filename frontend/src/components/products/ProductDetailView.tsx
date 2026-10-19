"use client";

import { defineCopy, useCopy, useSeparators } from "@/lib/i18n";
import type { ProductDetail } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    code: "产品代码",
    issuer: "管理人",
    type: "产品类型",
    risk: "风险等级",
    liquidity: "流动性",
    settlement: "赎回到账",
    minimum: "起购金额",
    inception: "成立日",
    maturity: "到期日",
    openEnded: "无固定期限",
    scope: "投资范围与策略",
    fees: "产品费用",
    feeNote: "年化费用逐日计提，已体现在净值中；申赎费在交易时收取。",
    metrics: "收益指标",
    basis: (b: string) => `测算依据：${b}`,
    benchmarkNote: "业绩比较基准不是预期收益率，不代表产品的未来表现和实际收益。",
    fictional: "虚构演示产品：机构与产品均不存在，信息仅供演示。",
  },
  en: {
    code: "Code",
    issuer: "Manager",
    type: "Type",
    risk: "Risk level",
    liquidity: "Liquidity",
    settlement: "Redemption settles",
    minimum: "Minimum",
    inception: "Inception",
    maturity: "Maturity",
    openEnded: "Open-ended",
    scope: "Investment scope and strategy",
    fees: "Fees",
    feeNote: "Annual fees accrue daily and are reflected in NAV; subscription and redemption fees apply per trade.",
    metrics: "Return metrics",
    basis: (b: string) => `Basis: ${b}`,
    benchmarkNote: "A performance benchmark is not an expected return and does not indicate future or actual performance.",
    fictional: "Fictional demo product: the manager and product do not exist.",
  },
});

/** 产品详情。超出客户风险等级的产品也可查看条款，但顶部显著提示「不作推荐、无权限购买」。 */
export function ProductDetailView({ product }: { product: ProductDetail }) {
  const c = useCopy(COPY);
  const sep = useSeparators();
  const basics: [string, string][] = [
    [c.code, product.code],
    [c.issuer, product.issuer],
    [c.type, product.type_label],
    [c.risk, product.risk_level],
    [c.liquidity, product.lockup],
    [c.settlement, product.redemption_settlement],
    [c.minimum, product.minimum],
    [c.inception, product.inception_date],
    [c.maturity, product.maturity_date ?? c.openEnded],
  ];

  return (
    <div className="flex flex-col gap-5">
      {product.eligibility_messages.length > 0 && (
        <div
          role="alert"
          className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
            product.eligible ? "bg-notice-soft text-notice" : "bg-danger-soft text-danger"
          }`}
        >
          {product.eligibility_messages.map((m) => (
            <p key={m}>{m}</p>
          ))}
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
        {basics.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-ink-3">{k}</dt>
            <dd className="figures mt-0.5 font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      {product.risk_note && <p className="text-xs text-ink-2">{product.risk_note}</p>}

      <Section title={c.scope}>
        <p>{product.investment_scope}</p>
        <p className="mt-1 text-ink-2">{product.strategy}</p>
      </Section>

      <Section title={c.fees}>
        <table className="figures w-full text-sm">
          <tbody>
            {product.fees.map((f) => (
              <tr key={f.label} className="border-b border-line last:border-0">
                <th className="py-2 pr-3 text-left font-normal text-ink-2">{f.label}</th>
                <td className="py-2 text-right font-semibold">{f.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-ink-3">{c.feeNote}</p>
      </Section>

      <Section title={c.metrics}>
        <ul className="flex flex-col gap-2">
          {product.metrics.map((m) => (
            <li key={m.label}>
              <p>
                <span className="text-ink-2">
                  {m.label}
                  {sep.colon}
                </span>
                <span className="figures font-bold">{m.text}</span>
              </p>
              {m.basis && <p className="mt-0.5 text-xs text-ink-3">{c.basis(m.basis)}</p>}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-3">{c.benchmarkNote}</p>
      </Section>

      <p className="text-xs text-ink-3">{c.fictional}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="text-sm leading-6">
      <h3 className="mb-1.5 text-[15px] font-extrabold">{title}</h3>
      {children}
    </section>
  );
}
