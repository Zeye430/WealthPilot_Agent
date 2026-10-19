import type { Metadata } from "next";

import { OpsDashboard } from "@/components/ops/OpsDashboard";

export const metadata: Metadata = {
  title: "运维看板",
  description: "WealthPilot 演示：对话延迟、兜底率、合规规则命中、模型费用与系统健康状态",
};

export default function OpsPage() {
  return <OpsDashboard />;
}
