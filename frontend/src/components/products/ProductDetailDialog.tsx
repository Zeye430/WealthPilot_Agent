"use client";

import { useEffect, useRef, useState } from "react";

import { ProductDetailView } from "@/components/products/ProductDetailView";
import { PurchaseFlow } from "@/components/products/PurchaseFlow";
import { ApiError, getProduct } from "@/lib/api";
import type { ProductDetail } from "@/lib/types";

/**
 * 产品详情弹窗：先看条款，再买入。能否买入由后端判断（评级、在售状态、费率是否核实），
 * 不能买入时说明原因；未测评时提供「去测评」入口。
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
        .catch((e) => setError(e instanceof ApiError ? e.message : "产品加载失败"));
    }
    if (!code && dialog.open) dialog.close();
  }, [code]);

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
      className="m-auto w-[calc(100%-2rem)] max-w-2xl rounded-sm bg-surface p-0 text-ink backdrop:bg-ink/40"
    >
      <div className="flex max-h-[88vh] flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-rule px-5 py-4 sm:px-7">
          <div className="min-w-0">
            {buying && <p className="text-xs text-ink-2">买入</p>}
            <h2 id="product-title" className="font-serif text-xl font-bold">
              {product?.name ?? "产品详情"}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            className="shrink-0 rounded-sm px-2 py-1 text-sm text-ink-2 hover:bg-paper"
          >
            关闭
          </button>
        </header>

        {buying && product ? (
          <PurchaseFlow product={product} onBack={() => setBuying(false)} onDone={() => ref.current?.close()} />
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
              {error && <p className="text-sm text-danger">{error}</p>}
              {!product && !error && <p className="text-sm text-ink-2">加载中…</p>}
              {product && <ProductDetailView product={product} />}
            </div>
            {purchase && (
              <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-rule bg-paper px-5 py-3 sm:px-7">
                {purchase.allowed ? (
                  <>
                    <p className="text-xs text-ink-2">起购 {product?.minimum}，买入前请阅读产品说明书与风险揭示书。</p>
                    <button
                      type="button"
                      onClick={() => setBuying(true)}
                      className="rounded-sm bg-brand px-6 py-2 text-sm font-medium text-surface"
                    >
                      买入
                    </button>
                  </>
                ) : (
                  <>
                    <p className="min-w-0 flex-1 text-xs leading-5 text-ink-2">{purchase.reasons[0]}</p>
                    {needsAssessment ? (
                      <button
                        type="button"
                        onClick={onStartAssessment}
                        className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface"
                      >
                        去测评
                      </button>
                    ) : (
                      <span className="rounded-sm border border-rule px-4 py-2 text-sm text-ink-3">不可买入</span>
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
