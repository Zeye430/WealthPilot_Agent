// 与 backend/app/tools/calculation_tools.py 输出的 UI 块一一对应

export type CalculationResultBlock = {
  type: "calculation_result";
  title: string;
  formula: string | null;
  items: { label: string; value: string; unit: string }[];
  assumptions: string[];
  disclaimer: string;
};

export type LineChartBlock = {
  type: "line_chart";
  title: string;
  x_label: string;
  y_label: string;
  series: { name: string; points: { x: number; y: number }[] }[];
  note: string;
};

export type UIBlock = CalculationResultBlock | LineChartBlock;

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  ui_blocks: UIBlock[];
};

export type ChatResponse = {
  conversation_id: string;
  reply: { content: string; ui_blocks: UIBlock[] };
};
