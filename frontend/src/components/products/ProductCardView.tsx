import type { ProductCard } from "@/lib/types";

/** 产品卡片：对话中的产品列表与「产品浏览」页共用。收益数字始终带口径标签。 */
export function ProductCardView({
  product,
  onOpen,
}: {
  product: ProductCard;
  onOpen?: (code: string) => void;
}) {
  const unverified = product.data_quality === "UNVERIFIED";
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-serif text-base font-bold leading-snug">{product.name}</p>
          <p className="mt-1 flex flex-wrap gap-1.5 text-xs text-ink-2">
            <Tag>{product.issuer}</Tag>
            <Tag>{product.type_label}</Tag>
            <Tag>{product.lockup}</Tag>
          </p>
        </div>
        <span
          className="figures shrink-0 rounded-sm border border-ink-3 px-1.5 py-0.5 text-xs font-medium"
          title={product.risk_note ?? `风险等级 ${product.risk_level}`}
        >
          {product.risk_level}
        </span>
      </div>

      <div className="mt-3">
        <p className="text-xs text-ink-2">{product.metric.label}</p>
        <p className="figures font-serif text-xl font-bold">{product.metric.text}</p>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 text-xs">
        <div>
          <dt className="text-ink-3">起购金额</dt>
          <dd className="figures mt-0.5">{product.minimum}</dd>
        </div>
        <div>
          <dt className="text-ink-3">年化固定费用</dt>
          <dd className="figures mt-0.5">{product.annual_fee}</dd>
        </div>
      </dl>

      {product.risk_note && <p className="mt-2 text-xs leading-5 text-ink-2">{product.risk_note}</p>}
      {unverified &&
        product.warnings?.map((w) => (
          <p key={w} className="mt-2 border-l-2 border-notice bg-notice-soft px-2 py-1 text-xs text-ink-2">
            {w}
          </p>
        ))}

      <p className="mt-3 flex items-center justify-between text-[11px] text-ink-3">
        <span>虚构演示产品 {product.code}</span>
        {product.rank ? <span className="figures">排序第 {product.rank} 位</span> : unverified ? <span>不参与排序</span> : null}
      </p>
    </>
  );

  const className = "block h-full w-full rounded-sm border border-rule bg-surface p-4 text-left";
  return onOpen ? (
    <button type="button" onClick={() => onOpen(product.code)} className={`${className} hover:border-brand`}>
      {body}
    </button>
  ) : (
    <div className={className}>{body}</div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-sm bg-paper px-1.5 py-0.5">{children}</span>;
}
