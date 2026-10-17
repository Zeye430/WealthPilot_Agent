import type { ChatResponse } from "./types";

export class ApiError extends Error {}

export async function sendChat(
  message: string,
  conversationId: string | null,
): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
  } catch {
    throw new ApiError("无法连接服务器，请确认后端已启动。");
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((body) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    throw new ApiError(detail ?? `请求失败（${res.status}）`);
  }
  return res.json();
}

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
