"use client";

import { useState } from "react";

import { ApiError, confirmPurchase, previewPurchase } from "@/lib/api";
import type { ProductDetail, PurchasePreview, PurchaseResult } from "@/lib/types";

/**
 * 买入流程（演示，只做到确认页）：输入金额 → 确认页（金额、费用、文件确认、风险揭示）→ 演示结果。
 * 每一步都由后端重新校验评级、起购金额和可用余额；不下单、不扣款。
 */
export function PurchaseFlow({
  product,
  onBack,
  onDone,
}: {
  product: ProductDetail;
  onBack: () => void;
  onDone: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [preview, setPreview] = useState<PurchasePreview | null>(null);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [result, setResult] = useState<PurchaseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const value = Number(amount);
  const validAmount = amount !== "" && Number.isFinite(value) && value > 0;

  async function run<T>(action: () => Promise<T>, onOk: (data: T) => void) {
    setBusy(true);
    setError(null);
    try {
      onOk(await action());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "操作失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Body>
        <div role="status" className="rounded-sm border border-brand/40 bg-brand-soft px-4 py-4">
          <p className="font-serif text-lg font-bold text-brand">买入确认已完成</p>
          <p className="mt-1 text-sm leading-6 text-ink-2">{result.message}</p>
        </div>
        <Summary rows={[["产品", result.product_name], ["买入金额", result.amount ?? ""], ["申购费", result.subscription_fee ?? ""]]} />
        <Footer>
          <button type="button" onClick={onDone} className="rounded-sm bg-brand px-6 py-2 text-sm font-medium text-surface">
            完成
          </button>
        </Footer>
      </Body>
    );
  }

  if (preview?.allowed) {
    const allChecked = preview.documents.every((d) => acknowledged.includes(d.id));
    return (
      <Body>
        <Summary
          rows={[
            ["产品", `${preview.product_name}（${preview.risk_level}）`],
            ["买入金额", preview.amount ?? ""],
            ["申购费", `${preview.subscription_fee}（费率 ${preview.subscription_rate}）`],
            ["扣款账户", `活期账户，可用 ${preview.available_balance}`],
          ]}
        />
        <section className="mt-5">
          <h3 className="font-serif text-sm font-bold">风险揭示</h3>
          <p className="mt-1.5 border-l-2 border-notice bg-notice-soft px-3 py-2 text-sm leading-6 text-ink-2">
            {preview.risk_disclosure}
          </p>
        </section>
        <fieldset className="mt-5 space-y-2 text-sm">
          <legend className="font-serif font-bold">请阅读并确认</legend>
          {preview.documents.map((d) => (
            <label key={d.id} className="flex items-start gap-2 leading-6">
              <input
                type="checkbox"
                checked={acknowledged.includes(d.id)}
                onChange={(e) =>
                  setAcknowledged((a) => (e.target.checked ? [...a, d.id] : a.filter((x) => x !== d.id)))
                }
                className="mt-1.5 accent-[var(--brand)]"
              />
              <span>我已阅读并理解《{d.name}》</span>
            </label>
          ))}
        </fieldset>
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <Footer>
          <button type="button" onClick={() => setPreview(null)} className="rounded-sm border border-rule px-4 py-2 text-sm hover:border-ink-3">
            修改金额
          </button>
          <button
            type="button"
            disabled={!allChecked || busy}
            onClick={() => run(() => confirmPurchase(product.code, value, acknowledged), setResult)}
            className="rounded-sm bg-brand px-6 py-2 text-sm font-medium text-surface disabled:opacity-40"
          >
            确认买入
          </button>
        </Footer>
      </Body>
    );
  }

  return (
    <Body>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (validAmount) run(() => previewPurchase(product.code, value), setPreview);
        }}
      >
        <label htmlFor="purchase-amount" className="text-sm font-medium">
          买入金额
        </label>
        <div className="mt-2 flex items-center gap-2 rounded-sm border border-rule bg-surface px-3 focus-within:border-brand">
          <input
            id="purchase-amount"
            data-focus-ring="off"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
            placeholder={`${product.minimum}起购`}
            className="figures min-w-0 flex-1 bg-transparent py-3 font-serif text-2xl outline-none placeholder:font-sans placeholder:text-base placeholder:text-ink-3"
            autoFocus
          />
          <span className="text-sm text-ink-2">元</span>
        </div>
        <p className="mt-2 text-xs text-ink-3">
          {product.lockup}，起购 {product.minimum}。业绩比较基准不是预期收益率。
        </p>
        {preview && !preview.allowed && (
          <ul role="alert" className="mt-3 space-y-1 text-sm text-danger">
            {preview.errors.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <Footer>
          <button type="button" onClick={onBack} className="rounded-sm border border-rule px-4 py-2 text-sm hover:border-ink-3">
            返回详情
          </button>
          <button
            type="submit"
            disabled={!validAmount || busy}
            className="rounded-sm bg-brand px-6 py-2 text-sm font-medium text-surface disabled:opacity-40"
          >
            下一步
          </button>
        </Footer>
      </form>
    </Body>
  );
}

function Body({ children }: { children: React.ReactNode }) {
  return <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">{children}</div>;
}

function Footer({ children }: { children: React.ReactNode }) {
  return <div className="mt-6 flex flex-wrap justify-end gap-2">{children}</div>;
}

function Summary({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="figures mt-4 divide-y divide-rule rounded-sm border border-rule text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4 px-3 py-2">
          <dt className="text-ink-2">{k}</dt>
          <dd className="text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
