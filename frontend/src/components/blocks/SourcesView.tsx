"use client";

import { defineCopy, useCopy } from "@/lib/i18n";
import type { SourcesBlock } from "@/lib/types";

const COPY = defineCopy({
  zh: {
    label: "回答依据",
    cited: "依据",
    reference: "参考资料",
    meta: (label: string, version: string) => `${label}，${version}`,
    section: (s: string) => `（${s}）`,
    original: null as string | null,
  },
  en: {
    label: "Sources",
    cited: "Sources",
    reference: "Related material",
    meta: (label: string, version: string) => `${label}, ${version}`,
    section: (s: string) => ` (${s})`,
    original: "Source text in Chinese (shown as published, not translated)" as string | null,
  },
});

/** What the reply is based on: cited sources show as "Based on", retrieved but uncited ones as "References". Expandable to the regulation text and links. */
export function SourcesView({ block }: { block: SourcesBlock }) {
  const c = useCopy(COPY);
  return (
    <section className="max-w-2xl" aria-label={c.label}>
      <p className="text-xs font-bold text-ink-3">{block.cited ? c.cited : c.reference}</p>
      <ul className="mt-1.5 space-y-1.5">
        {block.items.map((item) => (
          <li key={item.id}>
            <details className="group rounded-2xl bg-fill px-4 py-3 text-sm">
              <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="figures rounded-full bg-brand-soft px-2 py-0.5 text-xs font-bold text-brand">
                  {item.id}
                </span>
                <span className="min-w-0 flex-1">
                  {item.title.replace(/^(知识库 K\d+ |Knowledge base K\d+: )/, "")}
                  {item.section && <span className="text-ink-2">{c.section(item.section)}</span>}
                </span>
                <span className="text-xs text-ink-3">{c.meta(item.source_label, item.version)}</span>
              </summary>
              <div className="mt-2 space-y-2 border-t border-line pt-2 text-xs leading-5 text-ink-2">
                {c.original && item.source_language === "zh" && (
                  <p className="font-semibold text-ink-3">{c.original}</p>
                )}
                <p className="whitespace-pre-line" lang={item.source_language === "zh" ? "zh-CN" : undefined}>
                  {item.excerpt}
                </p>
                {item.citations && item.citations.length > 0 && (
                  <ul className="list-disc space-y-1 pl-4">
                    {item.citations.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                )}
                {item.links && item.links.length > 0 && (
                  <p className="flex flex-wrap gap-x-3">
                    {item.links.map((l) => (
                      <a
                        key={l.url}
                        href={l.url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-semibold text-brand underline underline-offset-2"
                      >
                        {l.title}
                      </a>
                    ))}
                  </p>
                )}
              </div>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function SourceNote({ text }: { text: string }) {
  return <p className="text-xs text-ink-3">{text}</p>;
}
