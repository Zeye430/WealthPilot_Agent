import type {
  AssessmentResult,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  CustomerState,
  HandoffView,
  ProductDetail,
  ProductListResponse,
  PurchasePreview,
  PurchaseResult,
  Questionnaire,
  Reminder,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

/** 会话失效或未登录：回到登录页（会话令牌在 httpOnly Cookie 中，前端脚本读不到，也无需处理）。 */
function redirectToLogin() {
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const next = encodeURIComponent(window.location.pathname);
    // 会话失效时整页跳转，清掉页面中残留的客户数据（这里不在 React 组件内，无法使用 router）
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${next}`);
  }
}

/** 前端自己生成的错误提示也要随界面语言（后端提示已按 Cookie 返回对应语言） */
function en(): boolean {
  return typeof document !== "undefined" && document.documentElement.lang === "en";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError(en() ? "Can't reach the server. Check that the backend is running." : "无法连接服务器，请确认后端已启动。");
  }
  if (res.status === 401 && !path.startsWith("/api/v1/auth/")) redirectToLogin();
  if (!res.ok) {
    const detail = await res
      .json()
      .then((body) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    if (detail) throw new ApiError(detail, res.status);
    // Next.js 代理连不上后端时返回 500 且没有 detail，最常见的原因是后端未启动
    if (en()) {
      throw new ApiError(res.status >= 500 ? `The server isn't responding (${res.status}). Please try again shortly.` : `Request failed (${res.status})`);
    }
    throw new ApiError(
      res.status >= 500
        ? `后端服务无响应（${res.status}）：请确认后端已启动，可运行 ./scripts/dev.sh 一键启动。`
        : `请求失败（${res.status}）`,
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

// ---------- 登录 ----------

export type SessionUser = { username: string; display_name: string; role: "customer" | "rm" | "ops" };

export type LoginConfig = {
  access_code_required: boolean;
  hint: string | null;
  demo_accounts: SessionUser[];
};

export const getLoginConfig = () => request<LoginConfig>("/api/v1/auth/config");

export const login = (username: string, password: string, accessCode?: string) =>
  request<SessionUser>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password, access_code: accessCode || null }),
  });

export const logout = () => request<void>("/api/v1/auth/logout", { method: "POST" });

export const getSessionUser = () => request<SessionUser>("/api/v1/auth/me");

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

export const clearNeeds = () => request<CustomerState>("/api/v1/needs", { method: "DELETE" });

export const getProducts = (productType?: string) =>
  request<ProductListResponse>(
    `/api/v1/products${productType ? `?product_type=${productType}` : ""}`,
  );

export const getProduct = (code: string) =>
  request<ProductDetail>(`/api/v1/products/${encodeURIComponent(code)}`);

export const speechStatus = () =>
  request<{ available: boolean; max_seconds: number }>("/api/v1/speech/status");

/** 上传 16 kHz 单声道 WAV，返回识别文字（录音不在服务端保存）。 */
export async function transcribeSpeech(wav: Blob): Promise<{ text: string }> {
  let res: Response;
  try {
    res = await fetch("/api/v1/speech/transcribe", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "audio/wav" },
      body: wav,
    });
  } catch {
    throw new ApiError("无法连接服务器，请确认后端已启动。");
  }
  if (res.status === 401) redirectToLogin();
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => (typeof b.detail === "string" ? b.detail : null))
      .catch(() => null);
    throw new ApiError(detail ?? `识别失败（${res.status}）`, res.status);
  }
  return res.json();
}

export const listReminders = () => request<Reminder[]>("/api/v1/reminders");

export const createReminder = (productCode: string) =>
  request<Reminder>("/api/v1/reminders", {
    method: "POST",
    body: JSON.stringify({ product_code: productCode }),
  });

export const cancelReminder = (id: string) =>
  request<void>(`/api/v1/reminders/${id}`, { method: "DELETE" });

export const previewPurchase = (productCode: string, amount: number) =>
  request<PurchasePreview>("/api/v1/purchases/preview", {
    method: "POST",
    body: JSON.stringify({ product_code: productCode, amount }),
  });

export const confirmPurchase = (productCode: string, amount: number, acknowledged: string[]) =>
  request<PurchaseResult>("/api/v1/purchases/confirm", {
    method: "POST",
    body: JSON.stringify({ product_code: productCode, amount, acknowledged }),
  });

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

export function formatDate(iso: string, locale: "zh" | "en" = "zh"): string {
  return new Date(iso).toLocaleDateString(locale === "en" ? "en-US" : "zh-CN", {
    year: "numeric",
    month: locale === "en" ? "short" : "long",
    day: "numeric",
  });
}

/** 人民币金额：¥500,000.00（中英文统一写法，数字按地区分隔） */
export function formatMoney(value: number, locale: "zh" | "en" = "zh", decimals = 2): string {
  const n = value.toLocaleString(locale === "en" ? "en-US" : "zh-CN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `¥${n}`;
}

export function productRiskRange(maxRisk: string): string {
  return maxRisk === "PR1" ? "PR1" : `PR1–${maxRisk}`;
}

// ---------- 理财经理看板（理财经理账号登录后访问） ----------

export const rmApi = {
  list: () => request<RmHandoffRow[]>("/api/v1/rm/handoffs"),
  detail: (id: string) => request<RmHandoffDetail>(`/api/v1/rm/handoffs/${id}`),
  accept: (id: string) => request<HandoffView>(`/api/v1/rm/handoffs/${id}/accept`, { method: "POST" }),
  resolve: (id: string) => request<HandoffView>(`/api/v1/rm/handoffs/${id}/resolve`, { method: "POST" }),
};

export type RmHandoffRow = HandoffView & {
  customer_name: string;
  synced_at: string;
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
  sync_scope: string[];
  messages: { role: "user" | "assistant" | "rm"; content: string }[];
  events: { to: string; actor: string; at: string }[];
};

// ---------- 运维看板 ----------

export type HealthCheck = { ok: boolean; required: boolean; [key: string]: unknown };

export type OpsOverview = {
  window_hours: number;
  bucket_seconds: number;
  kpis: {
    turns: number;
    p50_ms: number;
    p95_ms: number;
    max_ms: number;
    fallback_rate: number;
    degraded_rate: number;
    error_rate: number;
    rewrite_rate: number;
    llm_error_rate: number;
    tool_error_rate: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
    cost_per_turn_usd: number;
  };
  outcomes: Record<string, number>;
  intents: Record<string, number>;
  guard: { decisions: Record<string, number>; rules: Record<string, number> };
  tools: Record<string, Record<string, number>>;
  series: { start: string; turns: number; p50_ms: number | null; p95_ms: number | null; problems: number }[];
  recent: {
    at: string;
    request_id: string;
    conversation_id: string | null;
    locale: string;
    intent: string | null;
    outcome: string;
    guard_decision: string | null;
    violation_codes: string[];
    latency_ms: number;
    llm_calls: number;
    tokens: number;
    tool_errors: number;
  }[];
  health: {
    status: "ready" | "not_ready";
    checks: Record<string, HealthCheck>;
    version: string;
    git_sha: string;
    catalog_version: string;
    uptime_seconds: number;
  };
};

export const opsApi = {
  overview: (hours: number) => request<OpsOverview>(`/api/v1/ops/overview?hours=${hours}`),
};
