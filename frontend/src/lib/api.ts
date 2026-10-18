import type {
  AssessmentResult,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  CustomerState,
  HandoffView,
  MessagesSince,
  ProductDetail,
  ProductListResponse,
  Questionnaire,
} from "./types";

export class ApiError extends Error {}

export const DEMO_USERS = [
  { id: "demo_customer_1", label: "演示客户 A" },
  { id: "demo_customer_2", label: "演示客户 B" },
];

// 当前演示身份，随每个请求以 X-Demo-User 发送（真实系统应替换为登录鉴权）
let demoUser = DEMO_USERS[0].id;

export function setDemoUser(id: string) {
  demoUser = id;
}

async function request<T>(path: string, init: RequestInit = {}, user = demoUser): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Demo-User": user, ...init.headers },
    });
  } catch {
    throw new ApiError("无法连接服务器，请确认后端已启动。");
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((body) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    if (detail) throw new ApiError(detail);
    // Next.js 代理连不上后端时返回 500 且没有 detail，最常见的原因是后端未启动
    throw new ApiError(
      res.status >= 500
        ? `后端服务无响应（${res.status}）：请确认后端已启动，可运行 ./scripts/dev.sh 一键启动。`
        : `请求失败（${res.status}）`,
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const sendChat = (message: string, conversationId: string | null) =>
  request<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });

export const getMe = () => request<CustomerState>("/api/v1/me");

export const getQuestionnaire = () => request<Questionnaire>("/api/v1/assessment/questionnaire");

export const submitAssessment = (answers: Record<string, string>) =>
  request<{ assessment_id: string; result: AssessmentResult }>("/api/v1/assessment", {
    method: "POST",
    body: JSON.stringify({ answers }),
  });

export const confirmAssessment = (assessmentId: string) =>
  request<CustomerState>(`/api/v1/assessment/${assessmentId}/confirm`, { method: "POST" });

export const resetDemo = () => request<void>("/api/v1/demo/reset", { method: "POST" });

export const listConversations = () => request<ConversationSummary[]>("/api/v1/conversations");

export const getConversation = (id: string) =>
  request<ConversationDetail>(`/api/v1/conversations/${id}`);

export const consentHandoff = (id: string) =>
  request<HandoffView>(`/api/v1/handoffs/${id}/consent`, { method: "POST" });

export const cancelHandoff = (id: string) =>
  request<HandoffView>(`/api/v1/handoffs/${id}/cancel`, { method: "POST" });

export const getMessagesSince = (conversationId: string, after: number) =>
  request<MessagesSince>(`/api/v1/conversations/${conversationId}/messages?after=${after}`);

export const clearNeeds = () => request<CustomerState>("/api/v1/needs", { method: "DELETE" });

export const getProducts = (productType?: string) =>
  request<ProductListResponse>(
    `/api/v1/products${productType ? `?product_type=${productType}` : ""}`,
  );

export const getProduct = (code: string) =>
  request<ProductDetail>(`/api/v1/products/${encodeURIComponent(code)}`);

const yuan = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatYuan(value: string | number): string {
  return yuan.format(typeof value === "string" ? Number(value) : value);
}

export function formatWan(value: number): string {
  const wan = value / 10000;
  return `${Number.isInteger(wan) ? wan : wan.toFixed(1)}万`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function productRiskRange(maxRisk: string): string {
  return maxRisk === "PR1" ? "PR1" : `PR1–${maxRisk}`;
}

// ---------- 理财经理看板（演示身份独立于客户） ----------

export const DEMO_RMS = [
  { id: "rm_li", label: "李经理（虚构）" },
  { id: "rm_zhou", label: "周经理（虚构）" },
];

export const rmApi = {
  list: (rm: string) => request<RmHandoffRow[]>("/api/v1/rm/handoffs", {}, rm),
  detail: (rm: string, id: string) => request<RmHandoffDetail>(`/api/v1/rm/handoffs/${id}`, {}, rm),
  accept: (rm: string, id: string) =>
    request<HandoffView>(`/api/v1/rm/handoffs/${id}/accept`, { method: "POST" }, rm),
  reply: (rm: string, id: string, text: string) =>
    request<HandoffView>(
      `/api/v1/rm/handoffs/${id}/messages`,
      { method: "POST", body: JSON.stringify({ text }) },
      rm,
    ),
  resolve: (rm: string, id: string) =>
    request<HandoffView>(`/api/v1/rm/handoffs/${id}/resolve`, { method: "POST" }, rm),
};

export type RmHandoffRow = HandoffView & {
  customer_name: string;
  consented_at: string | null;
  updated_at: string;
};

export type RmHandoffDetail = HandoffView & {
  summary: {
    reason: string;
    customer: {
      display_name: string;
      age: number;
      customer_tier: string;
      assets: { demand_deposit: string; time_deposit: string; liquid_total: string; holdings: { name: string; amount: string }[] };
    } | null;
    assessment: string;
    needs: { label: string; value: string }[];
    products_discussed: string[];
    open_questions: string[];
    recent_customer_messages: string[];
  };
  consent_scope: string[];
  messages: { role: "user" | "assistant" | "rm"; content: string }[];
  events: { to: string; actor: string; at: string }[];
};
