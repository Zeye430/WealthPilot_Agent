"use client";

import { useEffect, useRef, useState } from "react";

import { ProductDetailView } from "@/components/products/ProductDetailView";
import { ApiError, getProduct } from "@/lib/api";
import type { ProductDetail } from "@/lib/types";

/** 按代码加载并展示产品详情；code 为 null 时关闭。 */
export function ProductDetailDialog({ code, onClose }: { code: string | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <dialog
      ref={ref}
      onClose={() => {
        setProduct(null);
        setError(null);
        onClose();
      }}
      aria-labelledby="product-title"
      className="m-auto w-[calc(100%-2rem)] max-w-2xl rounded-sm bg-surface p-0 text-ink backdrop:bg-ink/40"
    >
      <div className="flex max-h-[88vh] flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-rule px-5 py-4 sm:px-7">
          <h2 id="product-title" className="font-serif text-xl font-bold">
            {product?.name ?? "产品详情"}
          </h2>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            className="shrink-0 rounded-sm px-2 py-1 text-sm text-ink-2 hover:bg-paper"
          >
            关闭
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
          {error && <p className="text-sm text-danger">{error}</p>}
          {!product && !error && <p className="text-sm text-ink-2">加载中…</p>}
          {product && <ProductDetailView product={product} />}
        </div>
      </div>
    </dialog>
  );
}
