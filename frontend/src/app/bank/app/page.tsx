import type { Metadata } from "next";

import { BankApp } from "@/components/bank/BankApp";

export const metadata: Metadata = {
  title: "知岸银行",
  description: "模拟的知岸银行手机银行（演示用）",
};

export default function BankAppPage() {
  return <BankApp />;
}
