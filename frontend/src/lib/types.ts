// 与后端 API 及 UI 块一一对应（backend/app/tools、backend/app/api）

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

export type AssessmentPromptBlock = {
  type: "assessment_prompt";
  variant: "invite" | "reminder";
  title: string;
  message: string;
};

export type UIBlock = CalculationResultBlock | LineChartBlock | AssessmentPromptBlock;

export type ChatMessage =
  | { role: "user" | "assistant"; content: string; ui_blocks: UIBlock[] }
  // 仅前端展示的系统提示（如「测评已完成」），不发送给后端
  | { role: "notice"; content: string; ui_blocks: [] };

export type AssessmentSummary = {
  rating: string;
  rating_name: string;
  max_product_risk: string;
  score: number;
  confirmed_at: string;
  expires_at: string;
};

export type CustomerState = {
  customer_id: string;
  permission: "ASSESSMENT_REQUIRED" | "ASSESSED";
  gate_reasons: string[];
  assessment: AssessmentSummary | null;
};

export type ChatResponse = {
  conversation_id: string;
  reply: { content: string; ui_blocks: UIBlock[] };
  state: CustomerState;
};

export type Questionnaire = {
  version: string;
  title: string;
  disclaimer: string;
  questions: {
    id: string;
    dimension: string;
    text: string;
    options: { id: string; text: string }[];
  }[];
};

export type AssessmentResult = {
  questionnaire_version: string;
  score: number;
  rating: string;
  rating_name: string;
  description: string;
  max_product_risk: string;
  vetoed: boolean;
  warnings: string[];
  notes: string[];
};
