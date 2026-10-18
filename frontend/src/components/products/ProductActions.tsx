"use client";

import { createContext, useContext, useState } from "react";

import { ProductDetailDialog } from "@/components/products/ProductDetailDialog";

type ProductActions = { open: (code: string) => void };

const Ctx = createContext<ProductActions>({ open: () => {} });

/**
 * 全局只挂载一个产品详情弹窗：对话中的产品卡片、产品页、配置图都通过 open(code) 打开它，
 * 详情、买入流程和「去测评」入口因此在所有地方保持一致。
 */
export function ProductActionsProvider({
  children,
  onStartAssessment,
}: {
  children: React.ReactNode;
  onStartAssessment: () => void;
}) {
  const [code, setCode] = useState<string | null>(null);
  return (
    <Ctx.Provider value={{ open: setCode }}>
      {children}
      <ProductDetailDialog
        code={code}
        onClose={() => setCode(null)}
        onStartAssessment={() => {
          setCode(null);
          onStartAssessment();
        }}
      />
    </Ctx.Provider>
  );
}

export const useProductActions = () => useContext(Ctx);
