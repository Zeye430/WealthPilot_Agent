import type { ProductDetail } from "@/lib/types";

/** 产品详情。超出客户风险等级的产品也可查看条款，但顶部显著提示「不作推荐、无权限购买」。 */
export function ProductDetailView({ product }: { product: ProductDetail }) {
  const basics = [
    ["产品代码", product.code],
    ["管理人", product.issuer],
    ["产品类型", product.type_label],
    ["风险等级", product.risk_level],
    ["流动性", product.lockup],
    ["赎回到账", product.redemption_settlement],
    ["起购金额", product.minimum],
    ["成立日", product.inception_date],
    ["到期日", product.maturity_date ?? "无固定期限"],
  ];

  return (
    <div className="space-y-5">
      {product.eligibility_messages.length > 0 && (
        <div
          role="alert"
          className={`border-l-2 px-3 py-2.5 text-sm leading-6 ${
            product.eligible ? "border-notice bg-notice-soft text-ink-2" : "border-danger bg-notice-soft text-ink"
          }`}
        >
          {product.eligibility_messages.map((m) => (
            <p key={m}>{m}</p>
          ))}
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        {basics.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-ink-3">{k}</dt>
            <dd className="figures mt-0.5">{v}</dd>
          </div>
        ))}
      </dl>
      {product.risk_note && <p className="text-xs text-ink-2">{product.risk_note}</p>}

      <Section title="投资范围与策略">
        <p>{product.investment_scope}</p>
        <p className="mt-1 text-ink-2">{product.strategy}</p>
      </Section>

      <Section title="产品费用">
        <table className="figures w-full text-sm">
          <tbody>
            {product.fees.map((f) => (
              <tr key={f.label} className="border-b border-rule last:border-0">
                <th className="py-1.5 pr-3 text-left font-normal text-ink-2">{f.label}</th>
                <td className="py-1.5 text-right">{f.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1.5 text-xs text-ink-3">年化费用逐日计提，已体现在净值中；申赎费在交易时收取。</p>
      </Section>

      <Section title="收益指标">
        <ul className="space-y-2">
          {product.metrics.map((m) => (
            <li key={m.label}>
              <p>
                <span className="text-ink-2">{m.label}：</span>
                <span className="figures">{m.text}</span>
              </p>
              {m.basis && <p className="mt-0.5 text-xs text-ink-3">测算依据：{m.basis}</p>}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-3">业绩比较基准不是预期收益率，不代表产品的未来表现和实际收益。</p>
      </Section>

      <p className="text-xs text-ink-3">虚构演示产品：机构与产品均不存在，信息仅供演示。</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="text-sm leading-6">
      <h3 className="mb-1.5 font-serif font-bold">{title}</h3>
      {children}
    </section>
  );
}
