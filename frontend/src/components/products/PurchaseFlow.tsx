"use client";

import { useState } from "react";

import { Button } from "@/components/ui";
import { ApiError, confirmPurchase, previewPurchase } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { ProductDetail, PurchasePreview, PurchaseResult } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    step: "第 4 步，共 4 步：买入",
    amount: "买入金额",
    yuan: "元",
    placeholder: (min: string) => `${min}起购`,
    amountHint: (lockup: string, min: string) => `${lockup}，起购 ${min}。业绩比较基准不是预期收益率。`,
    back: "返回详情",
    next: "下一步",
    product: "产品",
    fee: "申购费",
    feeValue: (fee: string, rate: string) => `${fee}（费率 ${rate}）`,
    account: "扣款账户",
    accountValue: (b: string) => `活期，可用 ${b}`,
    disclosure: "风险揭示",
    readConfirm: "请阅读并确认",
    readDoc: (name: string) => `我已阅读并理解《${name}》`,
    edit: "修改金额",
    confirm: "确认买入",
    done: "买入确认已完成",
    finish: "完成",
    demo: "演示系统：只到确认页，不会真实下单",
    failed: "操作失败，请重试。",
  },
  en: {
    step: "Step 4 of 4: Buy",
    amount: "Amount",
    yuan: "CNY",
    placeholder: (min: string) => `Minimum ${min}`,
    amountHint: (lockup: string, min: string) => `${lockup}. Minimum ${min}. A benchmark is not an expected return.`,
    back: "Back",
    next: "Continue",
    product: "Product",
    fee: "Subscription fee",
    feeValue: (fee: string, rate: string) => `${fee} (${rate})`,
    account: "Pay from",
    accountValue: (b: string) => `Savings, ${b} available`,
    disclosure: "Risk disclosure",
    readConfirm: "Read and confirm",
    readDoc: (name: string) => `I have read and understood the ${name}`,
    edit: "Edit amount",
    confirm: "Confirm purchase",
    done: "Purchase confirmed",
    finish: "Done",
    demo: "Demo only: no real order is placed",
    failed: "Something went wrong. Please try again.",
  },
});

/** 买入确认、预约提醒成功时派发（AppShell 据此更新办理进度第 4 步） */
export function notifyActed() {
  window.dispatchEvent(new Event("wp:acted"));
}

/**
 * 买入流程（演示，只做到确认页）：输入金额 → 确认页（金额、费用、文件确认、风险揭示）→ 演示结果。
 * 每一步都由后端重新校验评级、起购金额和可用余额；不下单、不扣款。
 */
export function PurchaseFlow({ product, onBack, onDone }: { product: ProductDetail; onBack: () => void; onDone: () => void }) {
  const c = useCopy(COPY);
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
      setError(e instanceof ApiError ? e.message : c.failed);
    } finally {
      setBusy(false);
    }
  }

  const footerClass = "mt-6 flex flex-col gap-2.5";

  if (result) {
    return (
      <Body>
        <div role="status" className="flex flex-col items-center gap-2 rounded-card bg-ok-soft px-5 py-6 text-center">
          <span className="text-lg font-extrabold text-ok">{c.done}</span>
          <span className="text-sm leading-6 text-ink-2">{result.message}</span>
        </div>
        <Summary rows={[[c.product, result.product_name], [c.amount, result.amount ?? ""], [c.fee, result.subscription_fee ?? ""]]} />
        <div className={footerClass}>
          <Button size="lg" onClick={onDone} className="w-full">
            {c.finish}
          </Button>
        </div>
      </Body>
    );
  }

  if (preview?.allowed) {
    const allChecked = preview.documents.every((d) => acknowledged.includes(d.id));
    return (
      <Body>
        <Step label={c.step} />
        <div className="mt-5 flex flex-col items-center gap-0.5">
          <span className="text-[13px] text-ink-3">{c.amount}</span>
          <span className="figures text-4xl font-extrabold tracking-tight">{preview.amount}</span>
        </div>
        <Summary
          rows={[
            [c.product, `${preview.product_name}（${preview.risk_level}）`],
            [c.fee, c.feeValue(preview.subscription_fee ?? "", preview.subscription_rate)],
            [c.account, c.accountValue(preview.available_balance)],
          ]}
        />
        <section className="mt-4 rounded-2xl bg-notice-soft px-4 py-3">
          <h3 className="text-[13px] font-extrabold text-notice">{c.disclosure}</h3>
          <p className="mt-1 text-[13px] leading-6 text-notice">{preview.risk_disclosure}</p>
        </section>
        <fieldset className="mt-5 flex flex-col gap-1 text-sm">
          <legend className="mb-2 font-extrabold">{c.readConfirm}</legend>
          {preview.documents.map((d) => (
            <label key={d.id} className="flex min-h-10 cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={acknowledged.includes(d.id)}
                onChange={(e) => setAcknowledged((a) => (e.target.checked ? [...a, d.id] : a.filter((x) => x !== d.id)))}
                className="h-5 w-5 accent-[var(--brand)]"
              />
              <span>{c.readDoc(d.name)}</span>
            </label>
          ))}
        </fieldset>
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <div className={footerClass}>
          <Button size="lg" disabled={!allChecked || busy} onClick={() => run(() => confirmPurchase(product.code, value, acknowledged), (r) => {
            setResult(r);
            notifyActed();
          })} className="w-full">
            {c.confirm}
          </Button>
          <Button variant="quiet" onClick={() => setPreview(null)} className="w-full">
            {c.edit}
          </Button>
          <span className="text-center text-xs text-ink-3">{c.demo}</span>
        </div>
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
        <Step label={c.step} />
        <label htmlFor="purchase-amount" className="mt-5 block text-center text-[13px] text-ink-3">
          {c.amount}
        </label>
        <div className="mt-1 flex items-baseline justify-center gap-2">
          <span className="text-3xl font-extrabold text-ink-3">¥</span>
          <input
            id="purchase-amount"
            data-focus-ring="off"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
            placeholder="0"
            aria-describedby="purchase-hint"
            className="figures w-48 bg-transparent text-center text-5xl font-extrabold tracking-tight outline-none placeholder:text-line"
            autoFocus
          />
        </div>
        <p id="purchase-hint" className="mt-3 text-center text-xs text-ink-3">
          {c.amountHint(product.lockup, product.minimum)}
        </p>
        {preview && !preview.allowed && (
          <ul role="alert" className="mt-4 flex flex-col gap-1 rounded-2xl bg-danger-soft px-4 py-3 text-sm text-danger">
            {preview.errors.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <div className={footerClass}>
          <Button type="submit" size="lg" disabled={!validAmount || busy} className="w-full">
            {c.next}
          </Button>
          <Button variant="quiet" onClick={onBack} className="w-full">
            {c.back}
          </Button>
        </div>
      </form>
    </Body>
  );
}

function Body({ children }: { children: React.ReactNode }) {
  return <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-2 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-7">{children}</div>;
}

function Step({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[13px] font-bold text-ink-2">{label}</span>
      <div className="grid grid-cols-4 gap-1.5">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="h-1 rounded-full bg-brand" />
        ))}
      </div>
    </div>
  );
}

function Summary({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="figures mt-4 divide-y divide-line rounded-2xl bg-fill px-4 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4 py-3">
          <dt className="text-ink-2">{k}</dt>
          <dd className="text-right font-semibold">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
