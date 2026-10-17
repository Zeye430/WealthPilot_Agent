"use client";

import { useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent, type Ref } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AssessmentPrompt } from "@/components/blocks/AssessmentPrompt";
import { CalculationSlip } from "@/components/blocks/CalculationSlip";
import { LineChartBlock } from "@/components/blocks/LineChartBlock";
import { SourceNote, SourcesView } from "@/components/blocks/SourcesView";
import { ComparisonTableView, ProductDetailCard, ProductListView } from "@/components/blocks/ProductBlocks";
import { ApiError, sendChat } from "@/lib/api";
import type { ChatMessage, CustomerState, UIBlock } from "@/lib/types";

const SUGGESTIONS = [
  "100万按每年5%复利10年是多少？",
  "什么是业绩比较基准？",
  "我有100万，想稳一点，有什么产品推荐？",
  "100万在2%、3%、4%三种年化下，10年后分别是多少？",
];

export type ChatHandle = { addNotice: (text: string) => void };

type Props = {
  ref?: Ref<ChatHandle>;
  onStartAssessment: () => void;
  onStateChange: (state: CustomerState) => void;
};

export function Chat({ ref, onStartAssessment, onStateChange }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    addNotice: (text) => setMessages((m) => [...m, { role: "notice", content: text, ui_blocks: [] }]),
  }));

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  async function submit(text: string) {
    const message = text.trim();
    if (!message || pending) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", content: message, ui_blocks: [] }]);
    setPending(true);
    try {
      const res = await sendChat(message, conversationId);
      setConversationId(res.conversation_id);
      setMessages((m) => [...m, { role: "assistant", ...res.reply }]);
      onStateChange(res.state);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "出现未知错误，请重试。");
      setMessages((m) => m.slice(0, -1));
      setInput(message);
    } finally {
      setPending(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // 中文输入法选词时按回车不应发送
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(input);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
          {messages.length === 0 ? (
            <EmptyState onPick={submit} />
          ) : (
            <ol className="space-y-8">
              {messages.map((m, i) => (
                <li key={i}>
                  {m.role === "user" && <UserMessage text={m.content} />}
                  {m.role === "assistant" && (
                    <AssistantMessage message={m} onStartAssessment={onStartAssessment} />
                  )}
                  {m.role === "notice" && <Notice text={m.content} />}
                </li>
              ))}
              {pending && (
                <li className="text-sm text-ink-2" aria-live="polite">
                  <span className="inline-block animate-pulse">正在思考…</span>
                </li>
              )}
            </ol>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="border-t border-rule bg-paper">
        <form
          className="mx-auto max-w-3xl px-4 py-4 sm:px-8"
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
        >
          {error && (
            <p role="alert" className="mb-2 text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex items-end gap-2 rounded-sm border border-rule bg-surface p-2 focus-within:border-brand">
            <label htmlFor="chat-input" className="sr-only">
              输入您的问题
            </label>
            <textarea
              id="chat-input"
              data-focus-ring="off"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="请输入您的问题"
              className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 outline-none placeholder:text-ink-3"
              maxLength={2000}
            />
            <button
              type="submit"
              disabled={pending || !input.trim()}
              className="h-10 shrink-0 rounded-sm bg-brand px-4 text-sm font-medium text-surface disabled:opacity-40"
            >
              发送
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            <span className="hidden sm:inline">Enter 发送，Shift + Enter 换行。</span>测算结果均为假设情景，不构成投资建议。
          </p>
        </form>
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="pt-6 sm:pt-16">
      <h1 className="font-serif text-2xl font-bold sm:text-3xl">您好，今天想了解些什么？</h1>
      <p className="mt-3 max-w-prose leading-7 text-ink-2">
        我可以解释理财知识，测算收益和费用。完成风险测评后，还能在您的风险等级范围内筛选产品。
      </p>
      <ul className="mt-8 grid gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => onPick(s)}
              className="h-full w-full rounded-sm border border-rule bg-surface px-4 py-3 text-left text-sm leading-6 hover:border-brand"
            >
              {s}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-sm bg-brand-soft px-4 py-2.5 leading-7 whitespace-pre-wrap">{text}</p>
    </div>
  );
}

function Notice({ text }: { text: string }) {
  return (
    <p role="status" className="border-y border-rule py-2 text-center text-sm text-ink-2">
      {text}
    </p>
  );
}

function AssistantMessage({
  message,
  onStartAssessment,
}: {
  message: ChatMessage;
  onStartAssessment: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="max-w-prose leading-7">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: (props) => <p className="my-2" {...props} />,
            ul: (props) => <ul className="my-2 list-disc pl-5" {...props} />,
            ol: (props) => <ol className="my-2 list-decimal pl-5" {...props} />,
            strong: (props) => <strong className="font-medium" {...props} />,
            // 模型常用表格做对比；外层可横向滚动，避免手机上撑破页面
            table: (props) => (
              <div className="my-3 overflow-x-auto rounded-sm border border-rule bg-surface">
                <table className="w-full border-collapse text-sm" {...props} />
              </div>
            ),
            th: (props) => <th className="border-b border-rule bg-paper px-3 py-2 text-left font-medium" {...props} />,
            td: (props) => <td className="border-b border-rule px-3 py-2 align-top last:border-b-0" {...props} />,
            blockquote: (props) => (
              <blockquote className="my-3 border-l-2 border-notice bg-notice-soft px-3 py-2 text-sm text-ink-2 [&>p]:my-0" {...props} />
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
      {message.ui_blocks.map((block, i) => (
        <Block key={i} block={block} onStartAssessment={onStartAssessment} />
      ))}
    </div>
  );
}

function Block({ block, onStartAssessment }: { block: UIBlock; onStartAssessment: () => void }) {
  switch (block.type) {
    case "calculation_result":
      return <CalculationSlip block={block} />;
    case "line_chart":
      return <LineChartBlock block={block} />;
    case "assessment_prompt":
      return <AssessmentPrompt block={block} onStart={onStartAssessment} />;
    case "product_list":
      return <ProductListView block={block} />;
    case "product_detail":
      return <ProductDetailCard block={block} />;
    case "comparison_table":
      return <ComparisonTableView block={block} />;
    case "sources":
      return <SourcesView block={block} />;
    case "source_note":
      return <SourceNote text={block.text} />;
    default:
      return null;
  }
}
