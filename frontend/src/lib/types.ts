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
  status: "ON_SALE" | "ENDED" | "UPCOMING";
  data_quality: "VERIFIED" | "UNVERIFIED";
  synthetic: boolean;
  rank?: number | null;
  rank_factors?: string;
  /** 匹配理由（期限、流动性、费用），不涉及收益 */
  highlights?: string[];
  /** 能否买入：由后端按评级、在售状态等规则判断 */
  purchasable?: boolean;
  warnings?: string[];
  /** 即将发售的新品：募集期与募集规模上限 */
  sale_window?: string | null;
  raise_limit?: string | null;
};

export type RemindState = { allowed: boolean; reminded: boolean; reason: string | null };

export type UpcomingProductsBlock = {
  type: "upcoming_products";
  items: (ProductCard & { reminded: boolean })[];
  note: string;
  disclaimer: string;
};

export type TierBenefitsBlock = {
  type: "tier_benefits";
  tier: { name: string; card_name: string };
  aum: string;
  benefits: string[];
  next_tier: {
    name: string;
    card_name: string;
    threshold: string;
    gap: string;
    progress: number;
    benefits: string[];
  } | null;
  projection: { aum: string; tier_name: string; reaches_next: boolean } | null;
  campaigns: { name: string; period: string; reward: string; rule: string }[];
  evaluation_rule: string;
};

export type Reminder = {
  id: string;
  product: ProductCard;
  created_at: string;
  delivery_note: string;
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
  purchase?: { allowed: boolean; reasons: string[] };
  remind?: RemindState | null;
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
  rating: { code: string; name: string; max_product_risk: string } | null;
  items: ProductCard[];
  upcoming: (ProductCard & { remind: RemindState })[];
  ranking_note: string;
};

export type PurchasePreview = {
  allowed: boolean;
  errors: string[];
  product_code: string;
  product_name: string;
  risk_level: string;
  amount: string | null;
  subscription_fee: string | null;
  subscription_rate: string;
  available_balance: string;
  documents: { id: string; name: string }[];
  risk_disclosure: string;
};

export type PurchaseResult = PurchasePreview & {
  status: "DEMO_NOT_PLACED";
  message: string;
  confirmed_at: string;
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

export type NeedsRow = { field: string; label: string; value: string | null; source: string | null };

export type NeedsUpdateBlock = { type: "needs_update"; items: NeedsRow[] };

export type AllocationBlock = {
  type: "allocation";
  title: string;
  passed: boolean;
  slices: {
    code: string;
    name: string;
    amount: number;
    amount_text: string;
    pct: number;
    pct_text: string;
    risk_level: string | null;
    lockup: string;
  }[];
  checks: { status: "OK" | "WARN" | "FAIL"; label: string; message: string }[];
  disclaimer: string;
};

export type AssetOverview = {
  total: number;
  liquid: number;
  wealth: number;
  tier: { name: string; card_name: string };
  next_tier: { name: string; threshold: number; gap: number; progress: number } | null;
  rm: { rm_name: string; rm_title: string; phone: string | null; wecom_url: string | null };
};

export type BaseProfileSummary = {
  display_name: string;
  age: number;
  customer_tier: string;
  kyc_verified: boolean;
  assigned_rm: string;
  assets: {
    demand_deposit: string;
    time_deposit: string;
    holdings: { code: string; name: string; amount: string }[];
    liquid_total: string;
    total: string;
  };
  source: string;
};

export type HandoffStatus = "PENDING" | "ACCEPTED" | "RESOLVED" | "CANCELLED" | "AWAITING_CONSENT" | "IN_PROGRESS";

export type HandoffView = {
  id: string;
  status: HandoffStatus;
  status_label: string;
  rm_name: string;
  reason: string;
};

/** 理财经理名片：只含理财经理信息与联系方式，不展示客户资料 */
export type RmContactBlock = {
  type: "rm_contact";
  rm_name: string;
  rm_title: string;
  phone: string | null;
  wecom_url: string | null;
  handoff_id: string;
  notice: string;
};

export type UIBlock =
  | RmContactBlock
  | UpcomingProductsBlock
  | TierBenefitsBlock
  | NeedsUpdateBlock
  | AllocationBlock
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
  profile: { base: BaseProfileSummary | null; needs: NeedsRow[]; overview: AssetOverview | null };
};

export type ChatResponse = {
  conversation_id: string;
  reply: { content: string; ui_blocks: UIBlock[] };
  state: CustomerState;
  handoff: HandoffView | null;
};

export type ConversationSummary = {
  id: string;
  title: string | null;
  updated_at: string;
  message_count: number;
};

export type ConversationDetail = {
  id: string;
  title: string | null;
  messages: { role: "user" | "assistant"; content: string; ui_blocks: UIBlock[] }[];
  handoff: HandoffView | null;
};

export type Questionnaire = {
  prefill: Record<string, string>;
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
