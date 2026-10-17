import type { AssessmentPromptBlock } from "@/lib/types";

/** 测评入口。invite：客户要产品时的完整卡片；reminder：常识回答后的一行提醒。 */
export function AssessmentPrompt({
  block,
  onStart,
}: {
  block: AssessmentPromptBlock;
  onStart: () => void;
}) {
  if (block.variant === "reminder") {
    return (
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
        完成风险测评后，我可以在您的风险等级范围内为您筛选产品。
        <button type="button" onClick={onStart} className="font-medium text-brand underline underline-offset-4">
          开始测评
        </button>
      </p>
    );
  }
  return (
    <div className="flex max-w-xl flex-wrap items-center justify-between gap-4 rounded-sm border border-brand/40 bg-brand-soft px-5 py-4">
      <div>
        <p className="font-serif font-bold">{block.title}</p>
        <p className="mt-1 text-sm leading-6 text-ink-2">{block.message}</p>
      </div>
      <button
        type="button"
        onClick={onStart}
        className="shrink-0 rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface"
      >
        开始测评
      </button>
    </div>
  );
}
