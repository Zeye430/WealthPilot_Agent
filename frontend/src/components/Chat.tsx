"use client";

import { useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent, type Ref } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AllocationView, NeedsUpdateNote } from "@/components/blocks/AllocationView";
import { AssessmentPrompt } from "@/components/blocks/AssessmentPrompt";
import { TierBenefitsView, UpcomingProductsView } from "@/components/blocks/BenefitBlocks";
import { CalculationSlip } from "@/components/blocks/CalculationSlip";
import { RmContactCard } from "@/components/blocks/HandoffBlocks";
import { LineChartBlock } from "@/components/blocks/LineChartBlock";
import { ComparisonTableView, ProductDetailCard, ProductListView } from "@/components/blocks/ProductBlocks";
import { SourceNote, SourcesView } from "@/components/blocks/SourcesView";
import { ReadAloud } from "@/components/ReadAloud";
import { Icon } from "@/components/ui";
import { VoiceInput } from "@/components/VoiceInput";
import { ApiError, getConversation, sendChat } from "@/lib/api";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { ChatMessage, CustomerState, UIBlock } from "@/lib/types";

/** 出现这些界面块，说明已经为客户匹配过产品（办理进度第 3 步） */
const MATCH_BLOCKS = new Set(["product_list", "product_detail", "comparison_table", "allocation", "upcoming_products"]);

const COPY = defineCopy({
  zh: {
    hello: "您好，今天想规划些什么？",
    intro: "我可以帮您做理财规划、解答理财问题、测算收益和费用。完成风险测评后，还能按您的需求匹配产品。",
    suggestions: [
      "我有20万，一年内用不到，想稳一点，有什么推荐？",
      "我有100万，帮我做个理财规划",
      "什么是业绩比较基准？",
      "100万按每年5%复利10年是多少？",
    ],
    placeholder: "输入问题，或按住麦克风说话",
    inputLabel: "输入您的问题",
    send: "发送",
    thinking: "正在思考…",
    hint: "Enter 发送，Shift + Enter 换行。测算结果均为假设情景，不构成投资建议。",
    loadFailed: "历史会话加载失败",
    unknownError: "出现未知错误，请重试。",
  },
  en: {
    hello: "What would you like to plan today?",
    intro: "I can help you plan, answer wealth questions, and estimate returns and fees. Once you complete your risk profile, I'll match products to your needs.",
    suggestions: [
      "I have ¥200,000 I won't need for a year. What's a steady option?",
      "Help me plan ¥1,000,000.",
      "What is a performance benchmark?",
      "What does ¥1,000,000 grow to at 5% a year for 10 years?",
    ],
    placeholder: "Ask, or hold the mic to talk",
    inputLabel: "Your question",
    send: "Send",
    thinking: "Thinking…",
    hint: "Enter to send, Shift + Enter for a new line. Projections are hypothetical, not investment advice.",
    loadFailed: "Couldn't load this conversation",
    unknownError: "Something went wrong. Please try again.",
  },
});

export type ChatHandle = { addNotice: (text: string) => void; send: (text: string) => void };

type Props = {
  ref?: Ref<ChatHandle>;
  /** 打开历史会话时传入；新对话为空 */
  initialConversationId?: string | null;
  onStartAssessment: () => void;
  onStateChange: (state: CustomerState) => void;
  onActivity?: () => void;
  onMatched?: () => void;
};

export function Chat({ ref, initialConversationId, onStartAssessment, onStateChange, onActivity, onMatched }: Props) {
  const c = useCopy(COPY);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    addNotice: (text) => setMessages((m) => [...m, { role: "notice", content: text, ui_blocks: [] }]),
    send: (text) => submit(text),
  }));

  // 打开历史会话：从服务端恢复消息（含界面块）
  useEffect(() => {
    if (!initialConversationId) return;
    getConversation(initialConversationId)
      .then((conv) => {
        setConversationId(conv.id);
        const restored = conv.messages.filter((m) => m.role === "user" || m.role === "assistant");
        setMessages(restored);
        if (restored.some((m) => m.ui_blocks.some((b) => MATCH_BLOCKS.has(b.type)))) onMatched?.();
      })
      .catch(() => setError(c.loadFailed));
    // 只在打开时加载一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId]);

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
      if (res.reply.ui_blocks.some((b) => MATCH_BLOCKS.has(b.type))) onMatched?.();
      onStateChange(res.state);
      onActivity?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : c.unknownError);
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
        <div className="mx-auto max-w-3xl px-5 py-4 lg:px-12 lg:py-6">
          {messages.length === 0 ? (
            <EmptyState onPick={submit} />
          ) : (
            <ol className="flex flex-col gap-6">
              {messages.map((m, i) => (
                <li key={i}>
                  {m.role === "user" && <UserMessage text={m.content} />}
                  {m.role === "assistant" && <AssistantMessage message={m} onStartAssessment={onStartAssessment} />}
                  {m.role === "notice" && <Notice text={m.content} />}
                </li>
              ))}
              {pending && (
                <li className="flex items-center gap-2 text-sm text-ink-2" aria-live="polite">
                  <span className="flex gap-1" aria-hidden>
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand [animation-delay:300ms]" />
                  </span>
                  {c.thinking}
                </li>
              )}
            </ol>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <form
        className="relative mx-auto flex w-full max-w-3xl items-center gap-2.5 px-4 pt-2 pb-3 lg:px-12 lg:pb-6"
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        {error && (
          <p role="alert" className="absolute inset-x-4 bottom-full mb-1 rounded-2xl bg-danger-soft px-4 py-2 text-sm text-danger lg:inset-x-12">
            {error}
          </p>
        )}
        <div className="flex min-h-13 min-w-0 flex-1 items-center gap-2 rounded-full bg-fill py-1.5 pr-1.5 pl-5 focus-within:ring-2 focus-within:ring-brand">
          <label htmlFor="chat-input" className="sr-only">
            {c.inputLabel}
          </label>
          <textarea
            ref={inputRef}
            id="chat-input"
            data-focus-ring="off"
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={c.placeholder}
            className="max-h-32 min-h-6 flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-6 outline-none placeholder:text-ink-3"
            maxLength={2000}
          />
          <button
            type="submit"
            aria-label={c.send}
            disabled={pending || !input.trim()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink text-canvas disabled:opacity-30"
          >
            <Icon name="send" size={18} strokeWidth={2.4} />
          </button>
        </div>
        <VoiceInput
          disabled={pending}
          onText={(text) => {
            // 识别结果填入输入框，客户确认或修改后再发送
            setInput((prev) => (prev.trim() ? `${prev.trim()}${text}` : text));
            inputRef.current?.focus();
          }}
        />
      </form>
      <p className="mx-auto hidden w-full max-w-3xl px-12 pb-3 text-xs text-ink-3 lg:block">{c.hint}</p>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const c = useCopy(COPY);
  return (
    <div className="pt-4 lg:pt-14">
      <h2 className="text-[28px] leading-tight font-extrabold tracking-tight lg:text-4xl">{c.hello}</h2>
      <p className="mt-3 max-w-prose text-[15px] leading-7 text-ink-2">{c.intro}</p>
      <ul className="mt-7 grid gap-2.5 sm:grid-cols-2">
        {c.suggestions.map((s) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => onPick(s)}
              className="h-full w-full rounded-card bg-fill px-5 py-4 text-left text-sm leading-6 font-semibold hover:bg-line"
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
      <p className="max-w-[82%] rounded-[20px] rounded-br-md bg-brand px-4 py-3 text-[15px] leading-6 whitespace-pre-wrap text-on-brand">
        {text}
      </p>
    </div>
  );
}

function Notice({ text }: { text: string }) {
  return (
    <p role="status" className="mx-auto w-fit rounded-full bg-ok-soft px-4 py-2 text-center text-sm font-semibold text-ok">
      {text}
    </p>
  );
}

function AssistantMessage({ message, onStartAssessment }: { message: ChatMessage; onStartAssessment: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      {message.content && (
        <div className="max-w-prose text-base leading-7">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: (props) => <p className="my-2" {...props} />,
              ul: (props) => <ul className="my-2 list-disc pl-5" {...props} />,
              ol: (props) => <ol className="my-2 list-decimal pl-5" {...props} />,
              strong: (props) => <strong className="font-bold" {...props} />,
              h2: (props) => <h3 className="mt-4 mb-1 text-[17px] font-extrabold" {...props} />,
              h3: (props) => <h3 className="mt-3 mb-1 text-base font-extrabold" {...props} />,
              // 模型常用表格做对比；外层可横向滚动，避免手机上撑破页面
              table: (props) => (
                <div className="my-3 overflow-x-auto rounded-2xl bg-fill">
                  <table className="w-full border-collapse text-sm" {...props} />
                </div>
              ),
              th: (props) => <th className="border-b border-line px-3 py-2 text-left font-bold" {...props} />,
              td: (props) => <td className="border-b border-line px-3 py-2 align-top last:border-b-0" {...props} />,
              blockquote: (props) => (
                <blockquote className="my-3 rounded-2xl bg-notice-soft px-4 py-3 text-sm text-notice [&>p]:my-0" {...props} />
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      )}
      {message.ui_blocks.map((block, i) => (
        <Block key={i} block={block} onStartAssessment={onStartAssessment} />
      ))}
      {message.content && <ReadAloud text={message.content} hasBlocks={message.ui_blocks.length > 0} />}
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
    case "rm_contact":
      return <RmContactCard block={block} />;
    case "upcoming_products":
      return <UpcomingProductsView block={block} />;
    case "tier_benefits":
      return <TierBenefitsView block={block} />;
    case "needs_update":
      return <NeedsUpdateNote block={block} />;
    case "allocation":
      return <AllocationView block={block} />;
    case "source_note":
      return <SourceNote text={block.text} />;
    default:
      return null;
  }
}
