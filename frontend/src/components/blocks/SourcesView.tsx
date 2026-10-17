import type { SourcesBlock } from "@/lib/types";

/** 回答依据：已引用的资料显示为「依据」，检索到但未引用的显示为「参考资料」。可展开查看法规原文与链接。 */
export function SourcesView({ block }: { block: SourcesBlock }) {
  return (
    <section className="max-w-2xl border-t border-rule pt-3" aria-label="回答依据">
      <p className="text-xs font-medium text-ink-2">{block.cited ? "依据" : "参考资料"}</p>
      <ul className="mt-1.5 space-y-1.5">
        {block.items.map((item) => (
          <li key={item.id}>
            <details className="group rounded-sm border border-rule bg-surface px-3 py-2 text-sm">
              <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="figures rounded-sm bg-brand-soft px-1.5 text-xs font-medium text-brand">
                  {item.id}
                </span>
                <span className="min-w-0 flex-1">
                  {item.title.replace(/^知识库 K\d+ /, "")}
                  {item.section && <span className="text-ink-2"> · {item.section}</span>}
                </span>
                <span className="text-xs text-ink-3">
                  {item.source_label}，{item.version}
                </span>
              </summary>
              <div className="mt-2 space-y-2 border-t border-rule pt-2 text-xs leading-5 text-ink-2">
                <p className="whitespace-pre-line">{item.excerpt}</p>
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
                        className="text-brand underline underline-offset-2"
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
