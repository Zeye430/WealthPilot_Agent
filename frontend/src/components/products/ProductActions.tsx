"use client";

import { createContext, useContext, useState } from "react";

import { ProductDetailDialog } from "@/components/products/ProductDetailDialog";

type ProductActions = { open: (code: string) => void };

const Ctx = createContext<ProductActions>({ open: () => {} });

/**
 * Only one product detail dialog is mounted app-wide: product cards in chat, the products page and allocation charts all open it via open(code),
 * so details, the purchase flow and the "take the assessment" entry stay consistent everywhere.
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
