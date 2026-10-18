"use client";

import { useState } from "react";

import type { RmContactBlock } from "@/lib/types";

/**
 * 理财经理名片：客户通过企业微信或电话直接联系，只展示理财经理信息，不展示客户资料。
 * 咨询要点已由系统同步到理财经理看板，名片上用一句话告知客户。
 * 演示数据没有真实联系方式：点击时说明真实环境中会发生什么，而不是拨打一个虚构号码。
 */
export function RmContactCard({ block }: { block: RmContactBlock }) {
  const [demoNote, setDemoNote] = useState<string | null>(null);
  const initial = block.rm_name.slice(0, 1);

  return (
    <div className="max-w-md rounded-sm border border-rule bg-surface px-5 py-4">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand font-serif text-lg font-bold text-surface"
        >
          {initial}
        </span>
        <div className="min-w-0">
          <p className="font-serif text-base font-bold">{block.rm_name}</p>
          <p className="text-xs text-ink-2">{block.rm_title}，您的专属理财经理</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <ContactButton
          label="企业微信联系"
          href={block.wecom_url}
          external
          onDemo={() => setDemoNote(`演示环境：真实部署时将打开企业微信，与${block.rm_name}发起会话。`)}
          primary
        />
        <ContactButton
          label="拨打电话"
          href={block.phone ? `tel:${block.phone}` : null}
          onDemo={() => setDemoNote(`演示环境：真实部署时将直接拨打${block.rm_name}的工作电话。`)}
        />
      </div>
      {demoNote && (
        <p role="status" className="mt-2 text-xs text-ink-2">
          {demoNote}
        </p>
      )}

      <p className="mt-3 border-t border-rule pt-3 text-xs leading-5 text-ink-2">{block.notice}</p>
    </div>
  );
}

function ContactButton({
  label,
  href,
  external = false,
  primary = false,
  onDemo,
}: {
  label: string;
  href: string | null;
  external?: boolean;
  primary?: boolean;
  onDemo: () => void;
}) {
  const className = `block rounded-sm px-3 py-2.5 text-center text-sm font-medium ${
    primary ? "bg-brand text-surface" : "border border-brand text-brand hover:bg-brand-soft"
  }`;
  if (href) {
    return (
      <a href={href} className={className} {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
        {label}
      </a>
    );
  }
  return (
    <button type="button" onClick={onDemo} className={className}>
      {label}
    </button>
  );
}
