"use client";

import { Button } from "@/components/ui";
import { defineCopy, useCopy } from "@/lib/i18n";
import type { AssessmentPromptBlock } from "@/lib/types";

const COPY = defineCopy({
  zh: { reminder: "完成风险测评后，我可以按您的需求匹配产品。", start: "开始测评" },
  en: { reminder: "Complete your risk profile and I'll match products to your needs.", start: "Start now" },
});

/** 测评入口。invite：客户要产品时的完整卡片；reminder：常识回答后的一行提醒。 */
export function AssessmentPrompt({ block, onStart }: { block: AssessmentPromptBlock; onStart: () => void }) {
  const c = useCopy(COPY);
  if (block.variant === "reminder") {
    return (
      <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-2">
        {c.reminder}
        <Button size="sm" variant="quiet" onClick={onStart}>
          {c.start}
        </Button>
      </p>
    );
  }
  return (
    <div className="flex max-w-xl flex-col gap-4 rounded-card bg-brand-soft p-5 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="font-extrabold">{block.title}</p>
        <p className="mt-1 text-sm leading-6 text-ink-2">{block.message}</p>
      </div>
      <Button onClick={onStart}>{c.start}</Button>
    </div>
  );
}
