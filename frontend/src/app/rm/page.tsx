import type { Metadata } from "next";

import { RmDashboard } from "@/components/rm/RmDashboard";

export const metadata: Metadata = {
  title: "理财经理看板",
  description: "WealthPilot 演示：理财经理接收并处理客户的人工服务请求",
};

export default function RmPage() {
  return <RmDashboard />;
}
