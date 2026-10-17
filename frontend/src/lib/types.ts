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

export type ProductCard = {
  code: string;
  name: string;
  issuer: string;
  type_label: string;
  risk_level: string;
  risk_note: string | null;
  lockup: string;
  minimum: string;
  annual_fee: string;
  metric: { type: string; label: string; text: string };
  status: "ON_SALE" | "ENDED";
  data_quality: "VERIFIED" | "UNVERIFIED";
  synthetic: boolean;
  rank?: number | null;
  rank_factors?: string;
  warnings?: string[];
};

export type ExcludedSummary = { reason: string; count: number };

export type ProductListBlock = {
  type: "product_list";
  title: string;
  items: ProductCard[];
  excluded: ExcludedSummary[];
  ranking_note: string;
  disclaimer: string;
};

export type ProductDetail = ProductCard & {
  investment_scope: string;
  strategy: string;
  redemption_settlement: string;
  inception_date: string;
  maturity_date: string | null;
  fees: { label: string; value: string }[];
  metrics: { label: string; text: string; basis: string | null }[];
  eligible: boolean;
  eligibility_messages: string[];
};

export type ProductDetailBlock = ProductDetail & { type: "product_detail" };

export type ComparisonTableBlock = {
  type: "comparison_table";
  columns: { code: string; name: string }[];
  rows: { label: string; values: string[]; metric?: boolean }[];
  notes: string[];
  disclaimer: string;
};

export type ProductListResponse = {
  catalog_version: string;
  rating: { code: string; name: string; max_product_risk: string };
  items: ProductCard[];
  excluded: ExcludedSummary[];
  ranking_note: string;
};

export type SourceItem = {
  id: string;
  title: string;
  section: string | null;
  source_label: string;
  version: string;
  excerpt: string;
  citations?: string[];
  links?: { title: string; url: string }[];
};

export type SourcesBlock = {
  type: "sources";
  confident: boolean;
  cited?: boolean;
  items: SourceItem[];
};

export type SourceNoteBlock = { type: "source_note"; variant: "general"; text: string };

export type UIBlock =
  | SourcesBlock
  | SourceNoteBlock
  | CalculationResultBlock
  | LineChartBlock
  | AssessmentPromptBlock
  | ProductListBlock
  | ProductDetailBlock
  | ComparisonTableBlock;

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
