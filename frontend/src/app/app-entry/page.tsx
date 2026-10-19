import type { Metadata } from "next";

import { AppEntry } from "@/components/bank/AppEntry";

export const metadata: Metadata = {
  title: "AI 理财助手",
  description: "从知岸银行手机银行进入 WealthPilot 理财助手",
};

export default function AppEntryPage() {
  return <AppEntry />;
}
