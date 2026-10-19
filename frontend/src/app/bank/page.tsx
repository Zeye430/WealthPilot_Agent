import type { Metadata } from "next";

import { BankStage } from "@/components/bank/BankStage";

export const metadata: Metadata = {
  title: "从手机银行进入",
  description: "演示：客户登录知岸银行手机银行，从「AI 理财助手」模块免密进入 WealthPilot",
};

export default function BankStagePage() {
  return <BankStage />;
}
