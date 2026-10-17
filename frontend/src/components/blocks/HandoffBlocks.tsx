"use client";

import { useState } from "react";

import { ApiError, cancelHandoff, consentHandoff } from "@/lib/api";
import type {
  HandoffConsentBlock,
  HandoffRelayBlock,
  HandoffStatusBlock,
  HandoffView,
} from "@/lib/types";

/**
 * 交接确认卡片：客户看到将分享哪些信息、交给谁，点击同意后才提交。
 * 这是唯一能把交接从「待确认」推进到「待接单」的操作。
 */
export function HandoffConsentCard({
  block,
  onChange,
}: {
  block: HandoffConsentBlock;
  onChange: (view: HandoffView) => void;
}) {
  const [status, setStatus] = useState(block.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: (id: string) => Promise<HandoffView>) {
    setBusy(true);
    setError(null);
    try {
      const view = await action(block.id);
      setStatus(view.status);
      onChange(view);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "操作失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  const { preview } = block;
  return (
    <div className="max-w-xl rounded-sm border border-brand/40 bg-surface px-5 py-4 text-sm">
      <p className="font-serif text-base font-bold">转给理财经理：{block.rm_name}</p>
      <p className="mt-1 text-xs text-ink-2">原因：{block.reason}</p>

      <p className="mt-3 text-xs font-medium text-ink-2">将与理财经理分享以下信息</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-2">
        {block.scope.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>

      <dl className="mt-3 space-y-1 rounded-sm bg-paper px-3 py-2 text-xs leading-5">
        <div>
          <dt className="inline text-ink-3">风险测评：</dt>
          <dd className="inline">{preview.assessment}</dd>
        </div>
        {preview.needs.length > 0 && (
          <div>
            <dt className="inline text-ink-3">本次需求：</dt>
            <dd className="inline">{preview.needs.join("；")}</dd>
          </div>
        )}
        {preview.products_discussed.length > 0 && (
          <div>
            <dt className="inline text-ink-3">已了解的产品：</dt>
            <dd className="inline">{preview.products_discussed.join("、")}</dd>
          </div>
        )}
        {preview.open_questions.length > 0 && (
          <div>
            <dt className="inline text-ink-3">待跟进问题：</dt>
            <dd className="inline">{preview.open_questions.join("；")}</dd>
          </div>
        )}
      </dl>

      {status === "AWAITING_CONSENT" ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => act(consentHandoff)}
            className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface disabled:opacity-40"
          >
            同意分享并提交
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => act(cancelHandoff)}
            className="rounded-sm border border-rule px-4 py-2 text-sm hover:border-ink-3"
          >
            暂不需要
          </button>
          <span className="text-xs text-ink-3">演示系统：理财经理为虚构角色，不会联系真实银行员工。</span>
        </div>
      ) : (
        <p className="mt-3 text-xs font-medium text-ink-2">
          {status === "CANCELLED" ? "已取消，未分享任何信息。" : "已提交，可在对话顶部查看最新状态。"}
        </p>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}

export function HandoffStatusNote({ block }: { block: HandoffStatusBlock }) {
  return (
    <p className="text-xs text-ink-2">
      人工服务：{block.status_label}（{block.rm_name}）
    </p>
  );
}

export function HandoffRelayNote({ block }: { block: HandoffRelayBlock }) {
  return <p className="text-xs text-ink-3">已发送给{block.rm_name}，AI 暂停回复。</p>;
}

const BANNER: Partial<Record<HandoffView["status"], (rm: string) => string>> = {
  PENDING: (rm) => `已提交给${rm}，等待接单。在此期间我仍可回答您的问题。`,
  ACCEPTED: (rm) => `${rm}已接单，您的消息将直接发送给理财经理。`,
  IN_PROGRESS: (rm) => `${rm}正在为您服务，AI 已暂停回复。`,
  RESOLVED: (rm) => `${rm}已结束本次服务，AI 恢复为您服务。`,
};

/** 对话顶部的人工服务状态条：文案与后台真实状态一一对应，不会把「待接单」说成「已接入」。 */
export function HandoffBanner({ handoff }: { handoff: HandoffView | null }) {
  const text = handoff && BANNER[handoff.status]?.(handoff.rm_name);
  if (!text || !handoff) return null;
  const active = handoff.status === "ACCEPTED" || handoff.status === "IN_PROGRESS";
  return (
    <div
      role="status"
      className={`border-b px-4 py-2 text-center text-sm sm:px-8 ${
        active ? "border-brand/30 bg-brand-soft text-brand" : "border-rule bg-paper text-ink-2"
      }`}
    >
      {text}
    </div>
  );
}
