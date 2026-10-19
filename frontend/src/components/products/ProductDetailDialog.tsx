"use client";

import { useEffect, useRef, useState } from "react";

import { ProductDetailView } from "@/components/products/ProductDetailView";
import { PurchaseFlow } from "@/components/products/PurchaseFlow";
import { RemindButton } from "@/components/products/UpcomingCard";
import { Button, Icon } from "@/components/ui";
import { ApiError, getProduct } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { ProductDetail } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    title: "产品详情",
    buying: "买入",
    close: "关闭",
    loading: "加载中…",
    loadFailed: "产品加载失败",
    buyHint: (min: string) => `起购 ${min}，买入前请阅读产品说明书与风险揭示书。`,
    buy: "买入",
    assess: "去测评",
    notBuyable: "不可买入",
    saleWindow: (w: string) => `募集期 ${w}，开售后需要您本人确认买入。`,
  },
  en: {
    title: "Product details",
    buying: "Buy",
    close: "Close",
    loading: "Loading…",
    loadFailed: "Couldn't load this product",
    buyHint: (min: string) => `Minimum ${min}. Read the prospectus and risk disclosure before buying.`,
    buy: "Buy",
    assess: "Take risk profile",
    notBuyable: "Not available",
    saleWindow: (w: string) => `Subscription period ${w}. You confirm the purchase yourself once it opens.`,
  },
});

/**
 * 产品详情：手机上是从底部弹出的面板，电脑上居中。先看条款，再买入。
 * 能否买入由后端判断（评级、在售状态、费率是否核实），不能买入时说明原因；未测评时提供「去测评」入口。
 */
export function ProductDetailDialog({
  code,
  onClose,
  onStartAssessment,
}: {
  code: string | null;
  onClose: () => void;
  onStartAssessment: () => void;
}) {
  const c = useCopy(COPY);
  const ref = useRef<HTMLDialogElement>(null);
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buying, setBuying] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (code && !dialog.open) {
      dialog.showModal();
      getProduct(code)
        .then(setProduct)
        .catch((e) => setError(e instanceof ApiError ? e.message : c.loadFailed));
    }
    if (!code && dialog.open) dialog.close();
  }, [code, c.loadFailed]);

  const purchase = product?.purchase;
  const needsAssessment = purchase?.reasons.some((r) => r.includes("测评")) ?? false;

  return (
    <dialog
      ref={ref}
      onClose={() => {
        setProduct(null);
        setError(null);
        setBuying(false);
        onClose();
      }}
      aria-labelledby="product-title"
      className="mx-0 mt-auto mb-0 w-full max-w-none rounded-t-3xl bg-surface p-0 text-ink backdrop:bg-navy/50 sm:m-auto sm:w-[calc(100%-2rem)] sm:max-w-2xl sm:rounded-3xl"
    >
      <div className="flex max-h-[92vh] flex-col sm:max-h-[88vh]">
        <span aria-hidden className="mx-auto mt-3 h-1 w-10 rounded-full bg-line sm:hidden" />
        <header className="flex items-start justify-between gap-4 px-5 pt-4 pb-2 sm:px-7 sm:pt-6">
          <div className="min-w-0">
            <p className="text-[13px] text-ink-3">{buying ? c.buying : c.title}</p>
            <h2 id="product-title" className="text-[22px] leading-tight font-extrabold tracking-tight">
              {product?.name ?? c.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            aria-label={c.close}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-fill hover:bg-line"
          >
            <Icon name="close" size={18} />
          </button>
        </header>

        {buying && product ? (
          <PurchaseFlow product={product} onBack={() => setBuying(false)} onDone={() => ref.current?.close()} />
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-7">
              {error && <p className="text-sm text-danger">{error}</p>}
              {!product && !error && <p className="text-sm text-ink-2">{c.loading}</p>}
              {product && <ProductDetailView product={product} />}
            </div>
            {product?.remind && (
              <footer className="flex flex-col gap-3 border-t border-line px-5 pt-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-7">
                <p className="text-xs leading-5 text-ink-2">{c.saleWindow(product.sale_window ?? "")}</p>
                {!product.remind.allowed && needsAssessment ? (
                  <Button onClick={onStartAssessment} className="w-full">
                    {c.assess}
                  </Button>
                ) : (
                  <RemindButton
                    code={product.code}
                    initial={product.remind.reminded}
                    allowed={product.remind.allowed}
                    reason={product.remind.reason}
                  />
                )}
              </footer>
            )}
            {purchase && !product?.remind && (
              <footer className="flex flex-col gap-3 border-t border-line px-5 pt-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-7">
                {purchase.allowed ? (
                  <>
                    <p className="text-xs leading-5 text-ink-2">{c.buyHint(product?.minimum ?? "")}</p>
                    <Button size="lg" onClick={() => setBuying(true)} className="w-full">
                      {c.buy}
                    </Button>
                  </>
                ) : (
                  <>
                    <p className="text-xs leading-5 text-ink-2">{purchase.reasons[0]}</p>
                    {needsAssessment ? (
                      <Button size="lg" onClick={onStartAssessment} className="w-full">
                        {c.assess}
                      </Button>
                    ) : (
                      <Button size="lg" variant="quiet" disabled className="w-full">
                        {c.notBuyable}
                      </Button>
                    )}
                  </>
                )}
              </footer>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}
